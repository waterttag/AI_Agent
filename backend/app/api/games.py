"""
游戏 API 路由 (Games API Routes)
=================================
WHAT: 提供游戏的完整 CRUD、资源文件上传、AI 生成触发、游玩 HTML 直出、收藏切换等 REST 端点。
WHY:  游戏是平台的核心资源，所有游戏相关的操作集中在一个模块中，便于维护和测试。
      按功能分组: CRUD → Assets → Generation → Play HTML → Favorites。

关键技术决策:
1. game_url 使用 /api/games/{id}/play-html 端点而非 OSS 直链:
   - OSS 直链暴露了 bucket 名称和存储结构，增加安全风险
   - 通过 API 端点可以在服务端做鉴权（如只允许发布者访问草稿）
   - 如果将来换存储方案（从 OSS 到本地文件），前端 URL 不变
   - /play-html 直接返回数据库中的 HTML 内容，不依赖 MinIO/OSS

2. POST generate 从 Celery 回退到 threading:
   - Windows 不支持 Celery 的 prefork 进程池（fork 是 Unix 特性）
   - 开发环境可能没有 Redis，此时 celery_app.send_task 或 task.delay() 会抛异常
   - 回退方案用 daemon thread + asyncio.run() 在进程内执行，确保开发体验
   - 生产环境（Linux + Redis）走 Celery，可水平扩展

3. SQLite JSON 搜索使用 cast(Text).like 而非 JSON.contains:
   - SQLite 没有原生 JSONB 类型，JSON 列实际存储为 TEXT
   - JSON.contains 在 SQLite 中不可用，需要用 LIKE 做字符串匹配
   - cast(Text) 确保跨数据库兼容（PostgreSQL 也能执行）
   - 详见 game_service.py 的 list_games 函数
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.api.deps import get_current_user, get_optional_user
from app.models.user import User
from app.models.game import GameFavorite
from app.schemas.game import (
    GameCreate,
    GameUpdate,
    GameResponse,
    GameListResponse,
    GameAssetResponse,
    GenerateRequest,
)
from app.schemas.task import TaskResponse
from app.services import game_service, storage_service, task_service
from app.config import settings

# 创建路由实例，最终路径为 /api/games（因为顶层 api_router 有 /api 前缀）
router = APIRouter(prefix="/games", tags=["Games"])


# ============================================================================
# CRUD — 创建、读取、更新、删除
# ============================================================================

# ---------------------------------------------------------------------------
# POST /api/games — 创建游戏草稿
# ---------------------------------------------------------------------------
@router.post("", response_model=GameResponse, status_code=status.HTTP_201_CREATED)
async def create_game(
    data: GameCreate,                                  # Pydantic 验证的请求体
    db: AsyncSession = Depends(get_db),               # 数据库连接
    current_user: User = Depends(get_current_user),  # 强制登录
):
    """
    创建一个新的游戏草稿（状态为 "draft"，未发布）。

    行为:
        1. 调用 game_service.create_game() 写入数据库
        2. 重新查询游戏（带 eager-loaded assets）以生成完整响应
           WHY: create_game 返回的对象可能没有加载关联表（assets、author），
                直接序列化会遇到懒加载问题（异步 greenlet 错误）
        3. 手动设置 author_name（因为 GameResponse.author_name 不是 ORM 字段，
           需要从关联的 author 对象获取）

    技术说明:
        - game_service.create_game 内部做的 db.refresh() 不会自动加载 relationships，
          因为 SQLAlchemy 默认使用懒加载（lazy="select"），访问 .assets 时会发新查询
        - selectinload 在 get_game 中预加载，一次性 JOIN 查出所有关联数据
    """
    game = await game_service.create_game(db, current_user.id, data)

    # 重新查询: 用 selectinload 预加载 assets 和 author 关联
    # 避免后续序列化时触发懒加载导致的 greenlet 错误
    game = await game_service.get_game(db, game.id)

    # Pydantic model_validate: 将 ORM 对象转换为 schema，只取 schema 定义的字段
    resp = GameResponse.model_validate(game)

    # author_name 不在 Game ORM 表中，而是来自关联的 User 对象的 username 字段
    resp.author_name = current_user.username

    return resp


# ---------------------------------------------------------------------------
# GET /api/games — 游戏列表（分页、筛选）
# ---------------------------------------------------------------------------
@router.get("", response_model=GameListResponse)
async def list_games(
    status: str = Query(default="published"),               # 状态筛选: published / draft / preview
    tag: str | None = Query(default=None),                  # 标签筛选: 如 "射击"、"RPG"
    page: int = Query(default=1, ge=1),                     # 页码，从 1 开始，最小 1
    size: int = Query(default=12, ge=1, le=100),            # 每页条数，1-100，默认 12
    db: AsyncSession = Depends(get_db),
):
    """
    获取已发布的游戏列表，支持可选标签筛选和分页。

    筛选逻辑（在 game_service.list_games 中实现）:
        - status="listed" 特殊值 → 同时显示 published 和 preview 状态的游戏
        - 其他 status 值 → 精确匹配
        - tag 参数 → 在 JSON 数组中做 LIKE 搜索（因为 SQLite 无 JSONB 支持）

    分页:
        - page 从 1 开始（人类友好），内部转换为 (page-1)*size 的 OFFSET
        - size 限制最大 100，防止单次查询数据量过大
    """
    return await game_service.list_games(db, status=status, tag=tag, page=page, size=size)


# ---------------------------------------------------------------------------
# GET /api/games/{game_id} — 游戏详情
# ---------------------------------------------------------------------------
@router.get("/{game_id}", response_model=GameResponse)
async def get_game(
    game_id: str,
    db: AsyncSession = Depends(get_db),
    increment: bool = Query(default=False),    # 是否增加播放次数
):
    """
    获取单个游戏的详细信息。

    参数:
        - increment=true: 将此请求计入一次"游玩"(play_count + 1)
          WHY 用查询参数而非单独的 POST 端点:
            单独 POST /games/{id}/play 会增加前端实现复杂度（需要发两次请求：
            一次 GET 拿数据，一次 POST 记播放），而 increment 查询参数让前端在
            加载游戏详情时顺便标记播放，一次请求完成两件事。

    play_count 的防重复计数策略:
        前端通过 increment=true 参数控制 — 只有用户实际加载/游玩游戏时才传。
        浏览器刷新虽然会再次请求，但前端可以判断如果是重复加载则不传 increment=true，
        或者由前端在 localStorage 中记录"已播放过的游戏 ID"来避免重复计数。

    响应中包含 author_name: 从关联的 User.username 获取，而非存储在 Game 表中。
    """
    game = await game_service.get_game(db, game_id)
    if not game:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game not found")

    resp = GameResponse.model_validate(game)

    # 设置作者名称（来自 User 表的 username 字段）
    if game.author:
        resp.author_name = game.author.username

    # 播放计数: increment=true 时 +1
    if increment:
        # 使用 `or 0` 防御性编程 — 如果 play_count 为 None（历史数据），当作 0 处理
        game.play_count = (game.play_count or 0) + 1
        await db.commit()  # 注意: 这里是直接 commit，不刷新 resp，resp 中的 play_count 还是旧值
                           # 但前端通常只关心响应中的其他字段，播放次数一般在下次请求时反映

    return resp


# ---------------------------------------------------------------------------
# PUT /api/games/{game_id} — 更新游戏
# ---------------------------------------------------------------------------
@router.put("/{game_id}", response_model=GameResponse)
async def update_game(
    game_id: str,
    data: GameUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    更新游戏元数据。只有作者本人可以更新。

    权限控制: 两步检查
        1. 游戏是否存在 → 404
        2. 是否是作者 → 403 Forbidden（即使游戏存在，非作者也无权修改）

    model_dump(exclude_unset=True):
        只包含客户端实际传了的字段，未传的字段不会被覆盖。
        例如: 客户端只传 {"title": "新标题"}，description 和 tags 保持原值不变。
    """
    game = await game_service.get_game(db, game_id)
    if not game:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game not found")
    if game.author_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your game")

    updated = await game_service.update_game(db, game_id, data)
    return GameResponse.model_validate(updated)


# ---------------------------------------------------------------------------
# DELETE /api/games/{game_id} — 删除游戏
# ---------------------------------------------------------------------------
@router.delete("/{game_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_game(
    game_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    删除游戏。只有作者本人可以删除。

    响应: 204 No Content — REST 标准，删除成功无返回体。
         前端收到 204 后应更新 UI（从列表中移除该游戏）。

    级联删除: SQLAlchemy ORM 中设置了 cascade 关系，删除 Game 时
             其关联的 assets 和 favorites 也会被自动删除（数据库层面通过外键 ON DELETE CASCADE）。
    """
    game = await game_service.get_game(db, game_id)
    if not game:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game not found")
    if game.author_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your game")

    await game_service.delete_game(db, game_id)


# ============================================================================
# Assets — 资源文件管理
# ============================================================================

# ---------------------------------------------------------------------------
# POST /api/games/{game_id}/assets — 上传资源文件
# ---------------------------------------------------------------------------
@router.post("/{game_id}/assets", response_model=GameAssetResponse)
async def upload_asset(
    game_id: str,
    file: UploadFile = File(...),                       # File(...) 表示必填，来自 multipart/form-data
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    为游戏上传资源文件（图片/音频/其他）。

    文件类型识别:
        - image/*   → asset_type = "image"
        - audio/*   → asset_type = "audio"
        - 其他      → asset_type = "reference"
        WHY: 前端需要知道文件类型来决定渲染方式（img 标签 vs audio 标签 vs 下载链接）

    存储流程:
        1. 读取文件内容和 MIME 类型
        2. 生成 OSS 存储路径: games/{game_id}/assets/{uuid}.{ext}
        3. 通过 storage_service 上传到 S3 兼容存储
        4. 在数据库中记录资源元数据（不存文件内容本身）

    注意:
        file.size 可能为 None（某些客户端不传 Content-Length），所以 asset 表的 file_size 字段允许 NULL。
    """
    game = await game_service.get_game(db, game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    if game.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your game")

    # ---- 根据 MIME 类型确定资源类型 ----
    # file.content_type 来自上传请求的 Content-Type 头，如 "image/png"、"audio/mpeg"
    mime = file.content_type or ""
    if mime.startswith("image/"):
        asset_type = "image"
    elif mime.startswith("audio/"):
        asset_type = "audio"
    else:
        asset_type = "reference"

    # ---- 上传到对象存储 ----
    # storage_service.upload_file 返回 (oss_key, oss_url)
    # oss_key: 存储路径，如 "games/game-123/assets/uuid.png"
    # oss_url: 公网访问 URL（根据配置自动选择 virtual-hosted 或 path 风格）
    oss_key, oss_url = await storage_service.upload_file(file, game_id)
    file_size = file.size

    # ---- 记录资源元数据到数据库 ----
    asset = await game_service.add_asset(
        db, game_id, asset_type, file.filename or "unknown", oss_key, oss_url, file_size
    )
    return GameAssetResponse.model_validate(asset)


# ---------------------------------------------------------------------------
# GET /api/games/{game_id}/assets — 获取资源列表
# ---------------------------------------------------------------------------
@router.get("/{game_id}/assets", response_model=list[GameAssetResponse])
async def list_assets(game_id: str, db: AsyncSession = Depends(get_db)):
    """列出某个游戏的所有资源文件（无需认证，公开读取）"""
    assets = await game_service.get_assets(db, game_id)
    # 列表推导式: 将每个 ORM 对象转为 Pydantic schema
    return [GameAssetResponse.model_validate(a) for a in assets]


# ---------------------------------------------------------------------------
# DELETE /api/games/{game_id}/assets/{asset_id} — 删除资源
# ---------------------------------------------------------------------------
@router.delete("/{game_id}/assets/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_asset(
    game_id: str,
    asset_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除资源文件（需作者权限）。注意: 目前只删除数据库记录，不删除 OSS 上的实际文件。"""
    game = await game_service.get_game(db, game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    if game.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your game")

    deleted = await game_service.delete_asset(db, asset_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Asset not found")


# ============================================================================
# Generation — AI 游戏生成
# ============================================================================

# ---------------------------------------------------------------------------
# POST /api/games/{game_id}/generate — 触发 AI 生成
# ---------------------------------------------------------------------------
@router.post("/{game_id}/generate", response_model=TaskResponse)
async def generate_game(
    game_id: str,
    data: GenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    启动 AI 游戏生成流程。

    这个端点是最复杂的端点之一，它需要协调:
        1. LLM 配置检查
        2. 游戏状态更新（draft → generating）
        3. 任务记录创建
        4. 异步执行的启动（Celery 或 threading 回退）

    架构设计 — Celery → threading 的 fallback 机制:
        =============================================
        首选方案: Celery 异步任务队列
            - 生产者: API 进程调用 generate_game_task.delay() 发送消息到 Redis broker
            - 消费者: 独立的 Celery worker 进程从 Redis 取消息执行
            - 优点:  解耦、可水平扩展、任务持久化、失败重试
            - 前提:  Redis 可用 + Celery worker 在运行

        回退方案: threading.Thread + asyncio 事件循环
            - 在 API 进程内启动一个 daemon 线程
            - 线程内部创建独立的 asyncio 事件循环来运行 async harness
            - 优点:  零依赖、开发环境即可运行
            - 缺点:  与 API 进程共享资源、重启丢失任务、无法横向扩展

        为什么需要 fallback？
            1. Windows 不支持 Celery 的 prefork 进程池（prefork 依赖 os.fork()，这是 Unix 专有系统调用）
               解决方案: 在 Windows 上使用 threading 或 solo 池，但我们的代码直接回退到 thread
            2. 开发环境中可能没有安装/启动 Redis
               此时 celery_app 的 broker 连接会失败，delay() 方法会抛异常
            3. 回退确保开发者在本地也能完整测试 AI 生成流程

    Celery prefork pool 在 Windows 上的问题详解:
        - prefork 是 Celery 的默认 worker 池，通过 os.fork() 创建子进程
        - fork() 是 POSIX 标准的一部分，Windows 没有这个系统调用
        - Windows 上运行 Celery worker 需要使用 --pool=solo 或 --pool=threads
        - 开发环境（Windows）建议直接用 threading fallback，生产（Linux）用 Celery
    """
    # ---- 步骤1: 检查 LLM 配置 ----
    # 如果未配置 LLM provider 或 API key，直接拒绝请求
    # 503 Service Unavailable: 服务器暂时无法处理请求（不是客户端错误）
    # 区别于 500: 500 是内部错误（代码 bug），503 是预期中的不可用状态
    if settings.llm_provider == "none" or not settings.llm_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI generation is not configured. Set LLM_PROVIDER and LLM_API_KEY in .env to enable.",
        )

    # ---- 步骤2: 权限和状态检查 ----
    game = await game_service.get_game(db, game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    if game.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your game")

    # ---- 步骤3: 更新游戏状态 ----
    game.status = "generating"       # 标记为"生成中"，前端显示 loading 状态
    game.prompt_text = data.prompt_text  # 保存用户的提示词

    # 收集已上传的资源文件 ID 列表，传给 AI agent 作为参考素材
    asset_ids = [a.id for a in game.assets]

    # ---- 步骤4: 创建任务记录 ----
    # 任务记录是前端轮询的依据 — 前端通过 GET /api/tasks/{task_id} 查询进度
    task = await task_service.create_task(
        db,
        game_id=game_id,
        user_id=current_user.id,
        prompt_text=data.prompt_text,
        config={"model_preference": data.model_preference},
    )

    # 提交上面所有数据库变更（游戏状态 + 任务记录）
    await db.commit()

    # ---- 步骤5: 启动异步生成 ----
    # 生成的 task_id 和 game_id 需要转为字符串，因为 Celery 任务参数需要 JSON 可序列化
    try:
        # === 方案 A: Celery（首选）===
        from app.tasks.game_gen import generate_game_task

        # .delay() 是 .apply_async() 的快捷方式，将任务消息发送到 Redis broker
        # 任务消息格式: {"task": "app.tasks.game_gen.generate_game_task", "args": [...], ...}
        # Celery worker 收到后从 Redis 反序列化、执行任务
        generate_game_task.delay(
            task_id=str(task.id),
            game_id=str(game_id),
            user_prompt=data.prompt_text,
            asset_ids=asset_ids,
        )

    except Exception:
        # === 方案 B: 进程内后台线程（Celery 不可用时的回退）===
        # 导入放在 except 块中，避免在正常路径加载不必要的模块
        import asyncio
        import threading
        from app.agent.harness import GameGenerationHarness
        from app.agent.adapters import create_adapter

        def _run_in_thread():
            """在独立线程中运行 asyncio 事件循环来执行 agent pipeline"""
            # 每个线程需要自己的事件循环（asyncio 事件循环是线程局部的）
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            # run_until_complete 阻塞当前线程直到异步任务完成
            loop.run_until_complete(
                GameGenerationHarness(create_adapter()).run(
                    task_id=str(task.id),
                    game_id=str(game_id),
                    user_prompt=data.prompt_text,
                    asset_ids=asset_ids,
                )
            )

        # daemon=True: 主进程退出时该线程自动终止，不会阻止程序退出
        # 风险: 如果 API 进程在生成过程中重启，任务会丢失且无恢复机制
        #       生产环境必须用 Celery 来保证任务持久化
        threading.Thread(target=_run_in_thread, daemon=True).start()

    # 立即返回任务对象（此时生成还在后台进行中）
    return TaskResponse.model_validate(task)


# ============================================================================
# Play HTML — 游戏 HTML 直出端点
# ============================================================================
from fastapi.responses import HTMLResponse


@router.get("/{game_id}/play-html", response_class=HTMLResponse)
async def play_game_html(game_id: str, db: AsyncSession = Depends(get_db)):
    """
    直接返回生成的游戏 HTML 内容（Content-Type: text/html）。

    WHY 使用此端点而非 OSS 直接 URL 作为 game_url:
        =================================================
        1. 安全性 (Security):
           - OSS 直链暴露 bucket 名称和内部路径结构
           - 通过 API 端点可以在未来添加鉴权逻辑（如只允许发布后的游戏被访问）
           - 可以添加访问日志、频率限制等中间件

        2. 灵活性 (Flexibility):
           - 存储方案切换（OSS → 本地文件 → CDN）时前端 URL 不变
           - 可以添加内容处理逻辑（如注入分析脚本、修改 HTML 头部）
           - 支持 A/B 测试：根据用户特征返回不同版本的 HTML

        3. 简易性 (Simplicity):
           - 不依赖 MinIO/OSS 服务 — HTML 直接存在数据库的 llm_response_raw 字段中
           - 减少基础设施依赖，降低部署复杂度

        4. 一致性 (Consistency):
           - 游戏的所有数据（元数据、HTML、资源）通过统一 API 访问
           - 前端不需要区分"API URL"和"静态文件 URL"

    实现: 查询该游戏最近一次成功生成的 GenerationTask，直接返回其 llm_response_raw 字段。
    """
    from sqlalchemy import select
    from app.models.task import GenerationTask

    # 查询最近完成的生成任务
    # .order_by(GenerationTask.completed_at.desc()): 取最近完成的
    # .limit(1): 只取一条
    # .where(GenerationTask.status == "completed"): 只要成功完成的
    result = await db.execute(
        select(GenerationTask)
        .where(GenerationTask.game_id == game_id, GenerationTask.status == "completed")
        .order_by(GenerationTask.completed_at.desc())
        .limit(1)
    )
    task = result.scalar_one_or_none()

    # 如果没有生成过 HTML，返回 404
    if not task or not task.llm_response_raw:
        raise HTTPException(status_code=404, detail="No generated HTML found for this game")

    # HTMLResponse 会自动设置 Content-Type: text/html
    # 浏览器收到后会直接渲染为网页（iframe 嵌入或新标签页打开）
    return HTMLResponse(content=task.llm_response_raw)


# ============================================================================
# Favorites — 收藏功能
# ============================================================================

# ---------------------------------------------------------------------------
# POST /api/games/{game_id}/favorite — 收藏/取消收藏
# ---------------------------------------------------------------------------
@router.post("/{game_id}/favorite")
async def toggle_favorite(
    game_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    切换收藏状态: 如果已收藏则取消，如果未收藏则添加。

    设计: 使用 toggle 模式（一个按钮同时做添加和删除），而非两个独立端点，
         因为前端通常是一个心的图标，点击切换填充/空心状态。
         前端无法提前知道当前状态，发 POST 后根据返回值更新 UI。

    为什么用 POST 而不是 PUT 或 PATCH？
        - PUT 要求幂等和完整资源替换（但不是）
        - PATCH 是部分更新（但这更接近"切换操作"）
        - POST 是最通用的"执行一个操作"的语义
        - 这是一个非幂等操作（每次请求结果可能不同），POST 是正确的 REST 动词

    响应: {"favorited": true} 或 {"favorited": false}
         前端根据此值更新收藏按钮的状态。
    """
    from sqlalchemy import select

    # 检查是否已收藏
    result = await db.execute(
        select(GameFavorite).where(
            GameFavorite.user_id == current_user.id,
            GameFavorite.game_id == game_id,
        )
    )
    fav = result.scalar_one_or_none()

    if fav:
        # 已收藏 → 取消收藏（删除记录）
        await db.delete(fav)
        await db.commit()
        return {"favorited": False}
    else:
        # 未收藏 → 添加收藏
        db.add(GameFavorite(user_id=current_user.id, game_id=game_id))
        await db.commit()
        return {"favorited": True}


# ---------------------------------------------------------------------------
# GET /api/games/{game_id}/favorite — 查询收藏状态 + 总数
# ---------------------------------------------------------------------------
@router.get("/{game_id}/favorite")
async def get_favorite_status(
    game_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    查询当前用户是否收藏了该游戏，以及该游戏的总收藏数。

    返回: {"favorited": true/false, "count": 42}

    使用场景:
        - 进入游戏详情页时，前端需要知道: 1) 心形图标填不填充 2) 旁边显示的数字
        - 前端同时发 GET /api/games/{id} 和 GET /api/games/{id}/favorite 来组装页面

    count 查询: 使用 SQL 的 func.count() 聚合函数，效率高（数据库内部计算的）。
    """
    from sqlalchemy import select, func

    # 查询当前用户的收藏记录
    result = await db.execute(
        select(GameFavorite).where(
            GameFavorite.user_id == current_user.id,
            GameFavorite.game_id == game_id,
        )
    )
    # 有记录 = 已收藏，无记录 = 未收藏
    favorited = result.scalar_one_or_none() is not None

    # 查询该游戏的总收藏人数
    # func.count() 生成 SELECT COUNT(*) FROM game_favorites WHERE game_id = ?
    count_result = await db.execute(
        select(func.count()).where(GameFavorite.game_id == game_id)
    )
    count = count_result.scalar() or 0  # scalar() 可能返回 None，防御性 or 0

    return {"favorited": favorited, "count": count}


# ============================================================================
# 注意: 用户的收藏游戏 ID 列表端点 GET /api/auth/me/favorites 定义在 auth.py 中。
# 原因: 避免与 /api/games/{game_id} 动态路由冲突。
#       如果在此文件定义 GET /api/games/favorites，FastAPI 可能将 "favorites"
#       解释为 game_id 的值，导致不可预期的行为。
# ============================================================================
