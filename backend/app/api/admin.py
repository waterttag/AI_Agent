"""
管理员 API 路由 (Admin API Routes)
===================================
WHAT: 提供种子数据注入、内部运维操作等管理端点。
WHY:  开发阶段需要快速注入预构建的 HTML 游戏到平台中，绕过 AI 生成流水线。
      正式环境应添加管理员权限校验（如 JWT role="admin" 检查）。

inject-game 端点设计目的:
    1. 开发测试: 无需启动完整的 LLM 调用链路即可创建测试游戏
    2. 种子数据: 平台首次部署时预置几个示例游戏，让用户有内容可玩
    3. 人工审核: 允许运营人员手动上传经过审核的 HTML 游戏
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.models.game import Game
from app.models.task import GenerationTask
from app.schemas.game import GameResponse
from app.schemas.task import TaskResponse
from app.services import game_service, task_service

router = APIRouter(prefix="/admin", tags=["Admin"])


# ============================================================================
# 请求体 Schema — 内联定义，因为只在 admin 端点使用
# ============================================================================
class InjectGameRequest(BaseModel):
    """
    种子游戏注入请求体。

    字段说明:
        - title:          游戏标题，1-200 字符
        - description:    游戏描述，最大 5000 字符
        - tags:           标签列表，如 ["射击", "RPG", "太空"]
        - html_content:  完整的游戏 HTML 代码，最小 100 字符（确保不是空文件）
        - author_username: 作者用户名，默认为 "democreator"（需已注册）
    """
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    tags: list[str] = Field(default_factory=list)
    html_content: str = Field(..., min_length=100)
    author_username: str = Field(default="democreator")


# ============================================================================
# POST /api/admin/inject-game — 直接注入预构建游戏
# ============================================================================
@router.post("/inject-game", response_model=GameResponse)
async def inject_game(data: InjectGameRequest, db: AsyncSession = Depends(get_db)):
    """
    将预构建的 HTML 游戏直接注入平台。

    该端点执行以下操作:
        1. 查找或验证指定的作者用户存在
        2. 创建一个 status="published" 的游戏记录
        3. 创建一个 status="completed" 的生成任务记录，包含 HTML 内容
        4. 返回完整的游戏响应

    流程细节:
        - 先创建游戏时 game_url 使用 GAME_ID_PLACEHOLDER 占位符，
          因为 game.id 在 commit 后才由数据库生成（UUID 由 Python 的 uuid4 分配，
          实际在 add 时就已知，但这里通过 refresh 确认）
        - commit + refresh 后更新 game_url 为正确的 /api/games/{id}/play-html
        - 同时创建一个 "完成" 状态的任务，使得 /play-html 端点可以查到 HTML 内容

    安全: 目前未做权限校验，任何知道此端点的人都可以注入游戏。
         正式环境应该:
         1. 添加 get_current_admin_user 依赖（检查 role == "admin"）
         2. 或者通过环境变量/API Key 进行认证
    """
    from sqlalchemy import select

    # ---- 步骤1: 查找或验证作者用户 ----
    # 必须先注册一个用户（如 "democreator"），否则注入失败
    result = await db.execute(select(User).where(User.username == data.author_username))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=404,
            detail=f"User '{data.author_username}' not found. Register first."
        )

    # ---- 步骤2: 创建游戏记录 ----
    # 状态直接设为 "published"，无需经过 draft → generating → published 流程
    game = Game(
        title=data.title,
        description=data.description,
        tags=data.tags,
        author_id=user.id,
        status="published",
        prompt_text="Pre-built seed game",  # 标记为种子游戏
        game_url=f"/api/games/GAME_ID_PLACEHOLDER/play-html",  # 占位符，commit 后修正
    )
    db.add(game)
    await db.commit()
    await db.refresh(game)  # 获取数据库生成的字段（id, created_at 等）

    # ---- 步骤3: 用真实 ID 更新 game_url ----
    # 为什么需要两步？因为 game.id 通常是应用层生成的 UUID，但实际上为了确保
    # 数据库中其他可能自动生成的字段（如时间戳）已就绪，先 commit 再刷新再更新
    game.game_url = f"/api/games/{game.id}/play-html"

    # ---- 步骤4: 创建完成状态的生成任务 ----
    # 这个任务记录承载了两个关键数据:
    #   1. llm_response_raw: 游戏的完整 HTML 代码（/play-html 端点读取此字段）
    #   2. result_oss_url:   也指向 play-html 端点（作为对外的"结果地址"）
    #
    # llm_response_raw 字段名称可能有些误导（种子游戏没有经过 LLM），
    # 但它确实是存储最终 HTML 的字段，复用了生成任务的表结构
    task = GenerationTask(
        game_id=game.id,
        user_id=user.id,
        status="completed",
        progress=100,                           # 100% 完成
        user_prompt_used="Seed game injection", # 标记为种子注入
        llm_response_raw=data.html_content,     # 核心: HTML 内容存在这里
        result_oss_url=f"/api/games/{game.id}/play-html",
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    # ---- 步骤5: 重新加载游戏（带关联数据）并返回 ----
    # 因为需要返回带 author 关联的完整响应，用 game_service.get_game（内部有 selectinload）
    game = await game_service.get_game(db, game.id)
    resp = GameResponse.model_validate(game)
    if game.author:
        resp.author_name = game.author.username
    return resp
