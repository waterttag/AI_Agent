"""
生成任务业务逻辑层 (Generation Task Business Logic)
=====================================================
WHAT: 封装生成任务的创建、查询、进度更新等核心生命周期管理。
WHY:  任务管理是 AI 生成功能的核心状态机，需要可靠的状态转换和持久化。

任务状态机 (Task State Machine):
    =============================================================
    pending ──→ processing ──→ completed
                    ↓
                  failed
    =============================================================

    pending:     任务已创建，等待 Worker 取走执行
    processing:  正在执行（LLM 调用 + 代码生成 + 打包）
    completed:   执行成功，HTML 已存储在 llm_response_raw
    failed:      执行失败，error_message 中有错误详情

时间戳管理:
    - created_at:  任务创建时间（数据库自动设置 default=utcnow）
    - started_at:  任务开始执行时间（第一次 progress>0 或 status="processing" 时设置）
    - completed_at: 任务完成/失败时间（status 变为 completed 或 failed 时设置）

这些时间戳用于:
    - 计算任务耗时（completed_at - started_at）
    - 前端展示"生成用时: 45秒"
    - 检测僵尸任务（started_at 很久但 completed_at 为空 → 可能卡死）
"""

from datetime import datetime, timezone  # timezone.utc: UTC 时区对象

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import GenerationTask


# ============================================================================
# create_task — 创建新任务
# ============================================================================
async def create_task(
    db: AsyncSession,
    game_id: str,
    user_id: str,
    prompt_text: str,
    config: dict | None = None,
) -> GenerationTask:
    """
    创建一个新的生成任务记录。初始状态为 "pending"，进度为 0。

    参数:
        game_id:     关联的游戏 ID
        user_id:     谁发起的生成请求
        prompt_text: 用户的提示词（如"做一个射击游戏"）
        config:      额外配置（如 model_preference: "deepseek" / "gpt-4"）

    任务记录的用途:
        1. 前端轮询: GET /api/tasks/{id} 获取进度
        2. 结果存储: llm_response_raw 存生成的 HTML
        3. 审计日志: 记录谁在什么时候生成了什么
        4. 版本历史: 一个游戏可能有多个生成任务记录
    """
    task = GenerationTask(
        game_id=game_id,
        user_id=user_id,
        status="pending",
        progress=0,
        user_prompt_used=prompt_text,
        config=config or {},   # 如果没有传 config，用空字典
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


# ============================================================================
# get_task — 查询单个任务
# ============================================================================
async def get_task(db: AsyncSession, task_id: str) -> GenerationTask | None:
    """
    通过任务 ID 查询任务记录。
    这是最频繁被调用的方法 — 前端轮询时每秒可能调用多次。
    """
    result = await db.execute(
        select(GenerationTask).where(GenerationTask.id == task_id)
    )
    return result.scalar_one_or_none()


# ============================================================================
# list_tasks_for_game — 查询游戏的所有任务
# ============================================================================
async def list_tasks_for_game(db: AsyncSession, game_id: str) -> list[GenerationTask]:
    """
    查询某个游戏的所有生成任务，按创建时间从新到旧排序。

    用途:
        - 查看生成历史（每次生成尝试）
        - 版本对比：用户可以看到不同提示词产生的不同结果
        - 重新生成：创建新任务前检查是否有正在进行的任务
    """
    result = await db.execute(
        select(GenerationTask)
        .where(GenerationTask.game_id == game_id)
        .order_by(GenerationTask.created_at.desc())  # 最新的在前
    )
    return list(result.scalars().all())


# ============================================================================
# update_task_progress — 更新任务进度
# ============================================================================
async def update_task_progress(
    db: AsyncSession,
    task_id: str,
    progress: int,                   # 0-100 的进度百分比
    status: str = "processing",      # 新状态
    result_oss_url: str | None = None,      # OSS 结果 URL
    error_message: str | None = None,       # 错误信息（失败时写入）
    llm_response_raw: str | None = None,    # LLM 原始响应（生成的 HTML）
    system_prompt_used: str | None = None,  # 使用的系统提示词
) -> GenerationTask | None:
    """
    更新任务进度和状态。这是任务生命周期中最重要的方法。

    调用时机:
        1. Agent 开始处理时:  progress=10,  status="processing"
        2. LLM 调用完成:     progress=70,  llm_response_raw="<html>..."
        3. HTML 打包完成:    progress=90
        4. 全部完成:         progress=100, status="completed", result_oss_url="..."
        5. 发生错误:         status="failed", error_message="Connection timeout"

    时间戳自动管理:
        - status 变为 "processing" 且 started_at 为空 → 设置 started_at
        - status 变为 "completed" 或 "failed" → 设置 completed_at
        WHY: 避免在每次更新时都刷新时间戳，只记录"开始"和"结束"两个关键时间点。

    参数默认值 None 的设计:
        大部分参数默认为 None，只有调用方实际传了值才更新对应字段。
        这避免了"不小心把字段清空"的问题。
        例如: 如果 result_oss_url 默认是 ""，调用 update_task_progress(..., progress=50)
             就会把 result_oss_url 覆盖为空字符串。
    """
    # 先查询任务是否存在
    task = await get_task(db, task_id)
    if not task:
        return None

    # ---- 基础字段更新 ----
    task.progress = progress
    task.status = status

    # ---- 时间戳管理 ----
    # 首次进入 processing 状态时记录开始时间
    if status == "processing" and task.started_at is None:
        task.started_at = datetime.now(timezone.utc)
        # 使用 timezone.utc 确保时区感知:
        #   - datetime.now(timezone.utc) 返回带 UTC 时区信息的 datetime 对象
        #   - datetime.utcnow() 返回不带时区信息的 naive datetime（不推荐）
        #   - 带时区的 datetime 在序列化和比较时更安全

    # 任务终止时记录结束时间
    if status in ("completed", "failed"):
        task.completed_at = datetime.now(timezone.utc)

    # ---- 可选字段更新（只更新传了值的字段）----
    if result_oss_url is not None:
        task.result_oss_url = result_oss_url
    if error_message is not None:
        task.error_message = error_message
    if llm_response_raw is not None:
        # 这个字段存储生成的完整 HTML，可能很大（几百 KB）
        # 当前设计中 HTML 直接存在数据库，对于大文件应考虑:
        #   - 压缩存储（gzip）
        #   - 存 OSS 然后在数据库只存 URL
        #   - 数据库字段类型改为 LONGTEXT / MEDIUMTEXT（MySQL）或直接用 TEXT（SQLite/PG 无大小限制差异不大）
        task.llm_response_raw = llm_response_raw
    if system_prompt_used is not None:
        task.system_prompt_used = system_prompt_used

    await db.commit()
    await db.refresh(task)
    return task
