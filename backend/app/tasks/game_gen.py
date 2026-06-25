"""
Celery 任务: AI 游戏生成 (Celery Task — AI Game Generation)
=============================================================
WHAT: 定义 Celery 任务 generate_game_task，将异步的 AI Agent Harness 包装为 Celery 任务。
WHY:  AI 游戏生成是耗时的异步操作（30 秒到 2 分钟），不能阻塞 API 请求。
      通过 Celery 将生成逻辑从 API 进程中分离到独立 Worker 进程。

架构数据流:
    ============================================================
    [FastAPI API 进程]
        │
        │ generate_game_task.delay(task_id, game_id, prompt, assets)
        ▼
    [Redis Broker]
        │  消息: {"task": "...", "args": ["task-id", "game-id", "..."]}
        ▼
    [Celery Worker 进程]
        │  1. 从 Redis 取消息
        │  2. 反序列化参数
        │  3. 调用 generate_game_task(task_id, game_id, prompt, assets)
        │  4. 内部用 asyncio.run() 运行异步 pipeline
        │  5. 更新数据库中的 task 状态
        ▼
    [数据库 (SQLite/PostgreSQL)]
        task.status = "completed"
        task.llm_response_raw = "<html>...</html>"
    ============================================================

    [前端轮询]
        GET /api/tasks/{task_id} → 读取数据库 → 返回进度

Celery 任务参数限制:
    由于 task_serializer="json"，所有参数必须是 JSON 可序列化的:
    - str, int, float, bool, None ✓
    - list, dict (元素也需 JSON 可序列化) ✓
    - Python 对象 (ORM 实例), datetime, set ✗
    因此 asset_ids 是 list[str] 而不是 list[GameAsset]

bind=True 的含义:
    bind=True 将任务实例本身作为第一个参数（self）传入。
    好处:
        - self.request.retries: 当前已重试次数
        - self.max_retries:     最大重试次数
        - self.retry(exc=...):  触发重试
    如果没有 bind=True，任务函数无法访问这些任务元信息。

max_retries=1, default_retry_delay=60:
    - 最多重试 1 次（总共执行 2 次: 第一次 + 一次重试）
    - 重试前等待 60 秒
    - 适用场景: LLM API 临时不可用（rate limit、网络抖动）
    - 不适合: 代码 bug（重试也不会成功）
"""

import asyncio
import logging

from app.celery_app import celery_app
from app.config import settings

logger = logging.getLogger(__name__)


# ============================================================================
# generate_game_task — Celery 任务入口
# ============================================================================
@celery_app.task(bind=True, max_retries=1, default_retry_delay=60)
def generate_game_task(
    self,                                   # bind=True 自动注入的任务实例
    task_id: str,                           # 数据库中的 task UUID
    game_id: str,                           # 数据库中的 game UUID
    user_prompt: str,                       # 用户的提示词
    asset_ids: list[str],                   # 已上传的资源文件 ID 列表
):
    """
    Celery 任务: 编排完整的 AI 游戏生成流水线。

    任务流程:
        1. 记录开始日志
        2. 通过 asyncio.run() 运行异步 pipeline
           WHY asyncio.run()?
           - Celery 任务是同步函数（def 不是 async def）
           - GameGenerationHarness.run() 是 async 函数
           - asyncio.run() 是同步代码中运行 async 函数的桥梁
           - 内部创建新的事件循环，运行完后自动关闭
        3. 成功 → 返回 {"status": "completed", "url": "..."}
        4. 失败 → 更新数据库为 failed → 判断是否重试

    asyncio.run() 在 Celery 中的使用注意事项:
        - 每个 Worker 进程一次只能运行一个 asyncio.run()（因为它会创建并独占事件循环）
        - 这正是我们想要的行为（一次处理一个生成任务）
        - worker_prefetch_multiplier=1 确保 Worker 不会同时处理多个任务
        - 如果 Worker 使用 --pool=threads，每个线程调用 asyncio.run() 会创建独立的事件循环

    _run_pipeline 是内部 async 函数，不会直接暴露给 Celery。
    分离的原因: Celery 任务最好保持为简单的同步入口，
              具体的异步逻辑在 _run_pipeline 中实现。
    """
    logger.info(f"Starting game generation: task={task_id}, game={game_id}")

    try:
        # ---- 执行异步生成流水线 ----
        # asyncio.run() 的三步:
        #   1. 创建一个新的事件循环
        #   2. 运行传入的协程直到完成
        #   3. 关闭事件循环
        # 注意: 如果当前线程已经有运行中的事件循环，asyncio.run() 会抛出 RuntimeError
        #       但在 Celery Worker 中，每个任务在独立的上下文执行，不会有冲突
        result = asyncio.run(_run_pipeline(task_id, game_id, user_prompt, asset_ids))

        # result 是最终的 HTML 页面 URL（或 play-html API 路径）
        return {"status": "completed", "url": result}

    except Exception as exc:
        # ---- 失败处理 ----
        logger.error(f"Game generation failed: task={task_id}, error={exc}", exc_info=True)

        # 将任务标记为失败（更新数据库）
        # 也用 asyncio.run() 因为 _mark_failed 需要数据库异步 session
        asyncio.run(_mark_failed(task_id, str(exc)))

        # ---- 重试逻辑 ----
        # self.request.retries: 当前是第几次重试（0 表示首次执行）
        # self.max_retries:     最多重试次数
        # 如果还可以重试 → 抛出 self.retry() 让 Celery 重新排队
        # 如果重试已用完 → 返回失败状态
        if self.request.retries < self.max_retries:
            # self.retry(exc=exc) 会:
            #   1. 抛出 Retry 异常（Celery 内部捕获）
            #   2. 将任务消息重新放入 Broker 队列
            #   3. 等待 default_retry_delay (60 秒) 后重新执行
            #   4. self.request.retries 自增 1
            raise self.retry(exc=exc)

        # 重试次数已用完 → 返回失败结果
        return {"status": "failed", "error": str(exc)}


# ============================================================================
# _run_pipeline — 异步生成流水线
# ============================================================================
async def _run_pipeline(
    task_id: str, game_id: str, user_prompt: str, asset_ids: list[str]
) -> str:
    """
    运行 AI 游戏生成流水线。

    这个函数是实际执行的业务逻辑，被 Celery 任务和 in-process fallback 共用。

    步骤:
        1. 创建 LLM 适配器 (create_adapter)
        2. 创建 GameGenerationHarness
        3. 执行 harness.run() → 返回结果的 OSS URL 或 play-html 路径

    导入放在函数内部 (lazy import):
        WHY: 这些模块依赖 SQLAlchemy 模型和其他数据库组件，
             如果在模块顶层导入，Celery worker 启动时就会加载所有模型，
             在 Windows 上可能导致导入顺序问题（先加载了模型再加载配置）。
             函数内导入确保在需要时才加载，且此时所有依赖都已就绪。
    """
    from app.database import async_session
    from app.agent.harness import GameGenerationHarness
    from app.agent.adapters import create_adapter
    from app.services import task_service, game_service, storage_service

    # 创建 LLM 适配器（封装了对具体 LLM provider 的调用）
    # create_adapter() 根据 settings.llm_provider 和 settings.llm_api_key 创建对应的适配器
    # 支持的 provider: deepseek, openai, anthropic 等
    adapter = create_adapter()

    # GameGenerationHarness 是生成流水线的协调器:
    #   1. 预处理: 组装 system prompt + user prompt + 资源上下文
    #   2. LLM 调用: 让 AI 生成完整的 HTML 游戏代码
    #   3. 后处理: 验证 HTML 完整性、注入必要的脚本、打包
    #   4. 存储: 更新数据库 + 可选上传 OSS
    harness = GameGenerationHarness(adapter)

    # 执行流水线，返回结果的 URL
    result_url = await harness.run(
        task_id=task_id,
        game_id=game_id,
        user_prompt=user_prompt,
        asset_ids=asset_ids,
    )

    return result_url


# ============================================================================
# _mark_failed — 标记任务失败
# ============================================================================
async def _mark_failed(task_id: str, error_message: str):
    """
    将任务和对应游戏标记为失败状态。

    数据库更新:
        1. task: status → "failed", error_message 写入
        2. game: status → "failed"（让用户知道生成失败）

    为什么要更新 game 的状态?
        - 让前端知道这个游戏的生成已失败（status 从 "generating" → "failed"）
        - 用户可以修改提示词后重新触发生成
        - 如果只更新 task 不更新 game，game 会一直停留在 "generating" 状态
    """
    from app.database import async_session
    from app.services import task_service, game_service

    # 创建独立的数据库 session（不使用 API 请求的 session）
    # Celery Worker 不在 API 请求上下文中，需要创建自己的 session
    async with async_session() as db:
        # 更新任务状态为失败
        task = await task_service.get_task(db, task_id)
        if task:
            await task_service.update_task_progress(
                db,
                task_id,
                progress=0,
                status="failed",
                error_message=error_message,
            )

            # 同步更新游戏状态
            # 注意: game_id 存在 task 记录中，不需要额外参数
            game = await game_service.get_game(db, task.game_id)
            if game:
                game.status = "failed"
                await db.commit()
