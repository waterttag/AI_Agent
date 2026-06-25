"""
任务 API 路由 (Task API Routes)
================================
WHAT: 提供 AI 生成任务的轮询（polling）、任务列表和 Agent 执行日志的 REST 端点。
WHY:  AI 生成是异步的（可能需要几十秒到几分钟），前端需要轮询任务状态来展示进度条。
      任务记录是前端和后端之间的"进度通信协议"。

轮询模式说明:
    1. 前端调用 POST /api/games/{id}/generate 获得 task_id
    2. 前端每隔 N 秒调用 GET /api/tasks/{task_id} 查询进度
    3. 任务完成后，前端调用 GET /api/games/{id}/play-html 获取生成的游戏
    整个流程类似"提交订单 → 轮询订单状态 → 获取结果"的异步任务模式。

Agent 日志端点说明:
    GET /api/tasks/games/{game_id}/log 返回最近一次生成的执行步骤，
    用于在前端展示"AI 正在做什么"的透明性信息，让用户了解大致的进度阶段。
    这不是实时日志（Agent 内部有独立的日志系统），而是基于任务记录中的时间戳
    构造的摘要性步骤描述。
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.task import TaskResponse, TaskLogResponse
from app.services import task_service

router = APIRouter(prefix="/tasks", tags=["Tasks"])


# ============================================================================
# GET /api/tasks/{task_id} — 轮询任务状态
# ============================================================================
@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),  # 必须登录 — 只能查自己的任务
):
    """
    获取生成任务的状态和进度（前端轮询用）。

    任务状态生命周期:
        pending     → 任务已创建，等待执行（在 Celery 队列中排队）
        processing  → 正在调用 LLM 生成代码
        completed   → 生成成功，HTML 已存入 llm_response_raw
        failed      → 生成失败，error_message 中有错误详情

    前端轮询逻辑:
        if status == "completed" → 停止轮询，跳转游戏页
        if status == "failed"    → 停止轮询，展示错误信息
        else                     → 更新进度条，继续轮询

    安全: 只能查看自己的任务（task.user_id == current_user.id）
    """
    task = await task_service.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    if task.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your task")

    return TaskResponse.model_validate(task)


# ============================================================================
# GET /api/tasks/games/{game_id} — 游戏的生成任务历史
# ============================================================================
@router.get("/games/{game_id}", response_model=list[TaskResponse])
async def list_tasks(
    game_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    列出某个游戏的所有生成任务（按创建时间从新到旧排序）。

    用途:
        - 查看历史生成记录
        - 检查是否有进行中的任务（避免重复提交）
        - 版本历史: 每次生成都是一次"尝试"，用户可以对比不同版本

    过滤: 只返回当前用户的任务（列表推导式过滤）。
         注意: 这个过滤是在 Python 侧做的，如果任务数量很大应该改为 SQL WHERE 过滤。
         当前数据量下问题不大。
    """
    tasks = await task_service.list_tasks_for_game(db, game_id)
    return [TaskResponse.model_validate(t) for t in tasks if t.user_id == current_user.id]


# ============================================================================
# GET /api/tasks/games/{game_id}/log — Agent 执行日志
# ============================================================================
@router.get("/games/{game_id}/log", response_model=TaskLogResponse)
async def get_task_log(
    game_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    获取最近一次生成任务的 Agent 执行日志。

    日志内容是基于任务记录时间戳的摘要性描述，而非实时日志流:
        - "Preprocess: Context assembled with system prompt" — 系统提示词已组装
        - "Generate: LLM call started at 2024-xx-xx" — LLM 调用开始
        - "Package: Completed at 2024-xx-xx" — 打包完成
        - "Upload: Stored at https://..." — 已上传到 OSS

    为什么是摘要而非实时日志？
        - 实时日志需要 WebSocket 或 SSE（Server-Sent Events），实现复杂度高
        - 摘要足够让用户了解当前进度阶段
        - 基于数据库记录，不需要额外的日志基础设施

    prompt_summary: 截取用户提示词的前 200 字符，便于前端展示"你提交了什么需求"。
    """
    # 获取该游戏的所有任务（按时间排序）
    tasks = await task_service.list_tasks_for_game(db, game_id)

    # 过滤当前用户的任务
    user_tasks = [t for t in tasks if t.user_id == current_user.id]
    if not user_tasks:
        raise HTTPException(status_code=404, detail="No generation tasks found")

    # list_tasks_for_game 已按 created_at DESC 排序，第一个就是最新的
    latest = user_tasks[0]

    # 根据任务记录中的时间戳构建执行步骤描述
    steps = []

    # 系统提示词已使用 → Preprocess 阶段完成
    if latest.system_prompt_used:
        steps.append("Preprocess: Context assembled with system prompt")

    # started_at 不为空 → Generate 阶段已经开始
    if latest.started_at:
        steps.append(f"Generate: LLM call started at {latest.started_at.isoformat()}")

    # completed_at 不为空 → Package 阶段完成
    if latest.completed_at:
        steps.append(f"Package: Completed at {latest.completed_at.isoformat()}")

    # result_oss_url 不为空 → 结果已上传/存储
    if latest.result_oss_url:
        steps.append(f"Upload: Stored at {latest.result_oss_url}")

    # 返回日志响应
    # prompt_summary 取用户提示词前 200 字符，防止超长提示词撑大响应
    return TaskLogResponse(
        task_id=latest.id,
        status=latest.status,
        progress=latest.progress,
        prompt_summary=latest.user_prompt_used[:200] if latest.user_prompt_used else None,
        agent_steps=steps,
        started_at=latest.started_at,
        completed_at=latest.completed_at,
    )
