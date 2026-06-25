"""FastAPI application entry point — serves API + frontend SPA.

本文件是 FastAPI 应用的主入口，负责：
1. 创建 FastAPI 应用实例（含 lifespan 生命周期管理）
2. 配置 CORS 中间件
3. 注册 API 路由
4. 在生产模式下手动托管前端 SPA 静态文件
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.config import settings
from app.database import engine, Base
from app.utils.s3_client import ensure_bucket
from app.api import api_router

# [前端构建目录定位]
# 需要智能定位前端构建产物目录，因为：
#   - 本地开发：项目根目录/frontend/dist
#   - Docker 部署：容器内 /app/frontend/dist
#
# 策略：
#   1. 从当前文件位置向上推算项目根目录（同 config.py 的逻辑）
#   2. 优先检查推算路径下的 frontend/dist/index.html
#   3. 如果不存在，尝试 Docker 路径（/app 是 Dockerfile 中的 WORKDIR）
#
# 这样做避免了硬编码路径，同一个代码库可以同时在本地和 Docker 中运行。
_BASE = Path(__file__).resolve().parent.parent.parent  # 项目根目录 (D:\AI_Agent)
_FRONTEND_DIST = _BASE / "frontend" / "dist"            # 前端构建输出
_SEED_DIR = _BASE / "seed" / "games"                    # 预置种子游戏目录

if not (_FRONTEND_DIST / "index.html").exists():
    # 如果上面的路径不成立（例如在 Docker 容器中），尝试 Docker 标准路径。
    # Dockerfile 中通常设置 WORKDIR /app，所以 /app 就是项目根目录。
    _DOCKER_BASE = Path(__file__).resolve().parent.parent  # /app (Docker WORKDIR)
    _FRONTEND_DIST = _DOCKER_BASE / "frontend" / "dist"
    _SEED_DIR = _DOCKER_BASE / "seed" / "games"

# [种子游戏定义]
# 这些是预置的游戏数据，在应用首次部署时自动导入数据库。
# 每个游戏对应 seed/games/ 目录下的一个 HTML 文件（可直接在浏览器中运行的独立游戏）。
# 存在这些种子游戏的好处：
#   - 新部署的应用不会"空无一物"，用户体验更好
#   - 展示平台支持的游戏类型和风格
#   - 在 LLM 不可用时（llm_provider="none"），平台仍然有可玩的游戏
_SEED_GAMES = [
    {"title": "Classic Snake", "description": "Control a growing snake, eat red apples, and avoid crashing into yourself. A timeless arcade classic reimagined for the browser.", "tags": ["arcade","classic","snake"], "file": "snake.html"},
    {"title": "Memory Match", "description": "Flip cards and find matching pairs of cute emojis. Test your memory with 8 pairs to discover. Track your moves and beat your best time!", "tags": ["puzzle","memory","casual"], "file": "memory.html"},
    {"title": "Breakout Blitz", "description": "Destroy all the colorful bricks with your ball and paddle. Classic brick-breaker action with vibrant visuals and satisfying gameplay.", "tags": ["arcade","classic","breakout"], "file": "breakout.html"},
]


async def _auto_seed():
    """自动种子数据注入：确保首次部署后有可用的演示用户和预置游戏。

    执行逻辑：
    1. 检查数据库中是否已有已发布的游戏
    2. 如果有，说明已经初始化过，直接返回（幂等性保证）
    3. 如果没有，创建演示用户和三款种子游戏
    4. 为每个种子游戏创建对应的 GenerationTask 记录

    为什么用函数内部 import（延迟导入）：
        _auto_seed 在 lifespan 启动阶段被调用，此时整个应用尚未完全初始化。
        将模型和工具函数的导入放在函数内部，可以避免循环导入问题——
        例如 models 可能依赖 database 模块，而 database 可能依赖其他尚未加载的模块。
        延迟导入确保在被调用时所有依赖链都已经就绪。
    """
    from app.database import async_session
    from sqlalchemy import select, func
    from app.models.user import User
    from app.models.game import Game
    from app.models.task import GenerationTask
    from app.utils.security import hash_password

    async with async_session() as db:
        # 检查是否已有已发布的游戏（通过 COUNT 查询判断是否已初始化）。
        # 使用 func.count() 做聚合查询比先 SELECT 所有行再判断 len() 高效得多。
        result = await db.execute(select(func.count()).select_from(Game).where(Game.status == "published"))
        count = result.scalar() or 0
        if count > 0:
            return  # 已经初始化过，幂等退出

        # 创建演示用户（如果不存在）。
        # 先查询后创建的模式（check-then-create）在并发场景下理论上存在竞态条件，
        # 但 _auto_seed 只在应用启动时单线程执行一次，不需要担心并发问题。
        result = await db.execute(select(User).where(User.email == "demo@aigame.dev"))
        user = result.scalar_one_or_none()
        if not user:
            user = User(
                username="democreator",
                email="demo@aigame.dev",
                password_hash=hash_password("demo123"),
                role="creator"
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)  # 刷新以获取数据库生成的自增 ID

        # 批量注入种子游戏。
        # 每个种子游戏：
        #   - 从 seed/games/ 目录读取 HTML 内容
        #   - 创建 Game 记录（状态直接设为 published）
        #   - 创建对应的 GenerationTask 记录（状态为 completed）
        # 这样游戏在首次访问时即可直接播放，无需经过生成流程。
        for seed in _SEED_GAMES:
            html_path = _SEED_DIR / seed["file"]
            if not html_path.exists():
                # 跳过不存在的种子文件，不阻塞整个初始化流程。
                # 这样即使部分种子文件丢失，应用仍能正常启动。
                continue
            html_content = html_path.read_text(encoding="utf-8")

            game = Game(
                title=seed["title"],
                description=seed["description"],
                tags=seed["tags"],
                author_id=user.id,
                status="published",
                prompt_text="Pre-built seed game",
            )
            db.add(game)
            await db.commit()
            await db.refresh(game)

            # 设置游戏播放 URL（通过 API 端点提供 HTML 内容）。
            game.game_url = f"/api/games/{game.id}/play-html"

            # 创建生成任务记录，标记为已完成。
            # 这样在前端"任务历史"页面可以看到种子游戏，保持数据一致性。
            task = GenerationTask(
                game_id=game.id,
                user_id=user.id,
                status="completed",
                progress=100,
                user_prompt_used="Seed game injection",
                llm_response_raw=html_content,
                result_oss_url=f"/api/games/{game.id}/play-html",
            )
            db.add(task)
            await db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI 应用的生命周期管理（替代已废弃的 on_event 钩子）。

    使用 asynccontextmanager 装饰器将异步生成器函数转为上下文管理器。
    yield 之前的代码在应用启动时执行，yield 之后的代码在应用关闭时执行。

    为什么用 lifespan 而不是 on_event：
    - FastAPI 推荐 lifespan 作为新的生命周期管理方式
    - lifespan 支持异步操作（on_event 对异步支持不完善）
    - 可以在单个函数中同时管理启动和关闭逻辑
    - 通过上下文管理器确保资源正确释放（即使发生异常）
    """
    # ===== 启动阶段 =====

    # 1. 创建数据库表结构。
    #    engine.begin() 获取一个连接，conn.run_sync() 在异步上下文中执行同步代码。
    #    Base.metadata.create_all 会自动为所有继承 Base 的模型创建对应的数据库表，
    #    但只创建不存在的表（幂等操作），不会修改已有表的结构。
    #    生产环境建议使用 Alembic 做数据库迁移，这里为简化部署采用了自动建表。
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # 2. 自动种子数据注入。
    #    使用 try/except 吞掉所有异常的原因：
    #    - _auto_seed 是"锦上添花"的功能，失败不应阻止应用启动
    #    - 可能的失败场景：数据库连接问题、表尚不存在、种子文件缺失
    #    - 如果在这个阶段抛出未捕获异常，整个应用将无法启动
    #    - 应用的核心功能（API + 数据库）不依赖种子数据，所以可以优雅降级
    try:
        await _auto_seed()
    except Exception:
        pass

    # 3. 确保 MinIO 存储桶存在。
    #    MinIO 是可选依赖——在本地开发或不需要文件存储的部署中可以跳过。
    #    同样吞掉异常，因为：
    #    - MinIO 服务可能未安装或未启动
    #    - 存储桶可能已经存在（幂等操作，出错也不影响已有桶）
    #    - 应用核心功能不依赖 MinIO（游戏 HTML 也可以通过 API 直接返回）
    try:
        ensure_bucket()
    except Exception:
        pass

    yield  # 应用运行期间在此暂停

    # ===== 关闭阶段 =====
    # 释放数据库引擎的所有连接。
    # engine.dispose() 会关闭连接池中的所有连接，释放相关资源。
    # 在 NullPool 模式下（SQLite），此调用主要确保所有打开的文件句柄被关闭。
    await engine.dispose()


# 创建 FastAPI 应用实例。
# - lifespan: 生命周期管理器，负责启动初始化和优雅关闭
# - title/description/version: OpenAPI 文档元信息（可在 /docs 页面看到）
app = FastAPI(
    title="AI Native Game Platform",
    description="AI-powered interactive game generation and distribution platform",
    version="0.1.0",
    lifespan=lifespan,
)

# [CORS 跨域中间件]
# 使用通配符 allow_origins=["*"] 允许任意来源的跨域请求。
# 为什么用 "*" 而不是 config.py 中的 cors_origins：
#   - 开发阶段：前端可以在任意端口运行（Vite 随机端口、其他工具等）
#   - 生产部署：可能通过多个域名访问
#   - 本项目并非敏感系统，放开 CORS 可以降低部署配置复杂度
# 注意：allow_origins=["*"] 与 allow_credentials=True 同时使用时，
# 部分浏览器会有警告，但功能不受影响。
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册 API 路由。
# api_router 汇总了所有子路由（auth、games、tasks、users 等），
# 这种集中注册方式让 main.py 保持简洁，路由组织由 api/__init__.py 负责。
app.include_router(api_router)


@app.get("/health")
async def health():
    """健康检查端点。

    用于：
    - Docker 容器的 HEALTHCHECK 指令
    - Kubernetes 的 liveness/readiness probe
    - 负载均衡器的后端健康检测
    - CI/CD 流程中的部署验证

    返回 200 状态码即表示应用正在运行。
    """
    return {"status": "ok"}


# ==================== 前端 SPA 托管（生产模式） ====================
# FastAPI 本身没有内置的静态文件 SPA 路由，需要手动配置。
# 生产环境下，后端同时提供 API 和前端静态文件，简化部署架构。
#
# SPA (Single Page Application) 的路由特点：
#   前端使用客户端路由（如 Vue Router / React Router），
#   所有非 API 路由（如 /games/123）都应该返回 index.html，
#   由前端 JavaScript 解析 URL 后渲染对应页面。
#   如果直接请求 /games/123 而服务端只返回 404，用户刷新页面就会看到错误。
#   这就是经典的 "SPA fallback" 问题。

if _FRONTEND_DIST.exists() and (_FRONTEND_DIST / "index.html").exists():
    # 前端已构建，启用完整 SPA 托管模式。

    # 挂载 /assets 目录，提供 JS、CSS、图片等静态资源。
    # StaticFiles 中间件直接映射文件系统路径到 URL 路径，
    # 例如 /assets/index-abc123.js -> frontend/dist/assets/index-abc123.js
    app.mount("/assets", StaticFiles(directory=_FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """SPA 回退路由：处理所有非 API 和非静态文件的 GET 请求。

        路由匹配逻辑：
        1. API 路由（/api/*, /health, /docs 等）已被 FastAPI 优先匹配
        2. /assets/* 被 StaticFiles 中间件处理
        3. 剩余所有 GET 请求进入此函数

        处理逻辑：
        1. 检查请求路径对应的文件是否存在（如 /favicon.ico）
        2. 如果文件存在，直接返回（支持非哈希命名的静态文件）
        3. 如果文件不存在，返回 index.html——由前端路由器接管

        这种模式的优势：
        - 前端和后端部署在同一个进程中，节省资源
        - 无需配置 Nginx 反向代理规则
        - 适合中小型项目的单体部署架构

        局限性（大型项目应考虑的）：
        - 后端进程同时处理静态文件，可能影响 API 响应时间
        - 不支持 CDN 加速（除非在前面加反向代理）
        - 缺少 Nginx 提供的 gzip、缓存控制等高级功能
        """
        file_path = _FRONTEND_DIST / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        # SPA fallback：所有前端路由都返回 index.html
        return FileResponse(_FRONTEND_DIST / "index.html")
else:
    # 前端未构建，返回提示信息（开发模式下的兜底）。
    # 此时应用仅提供 API 服务 + /docs 交互式文档，
    # 开发者可以单独启动前端开发服务器（如 npm run dev）。
    @app.get("/")
    async def root():
        return {
            "name": "AI Native Game Platform",
            "version": "0.1.0",
            "docs": "/docs",
            "tip": "Frontend not built. Run: cd frontend && npm run build",
        }
