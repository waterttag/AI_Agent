# ============================================================
# 种子数据脚本 — Seed Data Script
# ============================================================
# 功能：初始化数据库，注入 3 款示例游戏 + 1 个测试用户
# 支持本地开发和 Docker 两种运行模式（自动检测路径）
#
# 使用方式：
#   python seed/seed.py          # 默认 SQLite，需 MinIO 已运行
#   python seed/seed.py --pg     # PostgreSQL（docker-compose 环境下）
#
# 运行时机：
#   - 开发环境：docker compose up 时 seed 容器自动执行
#   - 生产环境：Railway 启动时后端 _auto_seed() 函数调用
#
# 幂等性：每次运行先清理再插入，可安全重复执行
# ============================================================

import asyncio
import sys
import os

# ---- 路径适配：同时支持 Docker 容器内和本地开发 ----
# Docker 容器内：后端代码在 /app/ 目录（由 Dockerfile COPY 而来）
# 本地开发：   后端代码在 backend/ 目录，种子脚本在 seed/ 目录
# 通过检测 /app/app 路径是否存在来判断运行环境
if os.path.exists("/app/app"):
    # Docker 环境：后端代码挂载在 /app/
    sys.path.insert(0, "/app")
    SEED_DIR = "/"                    # 游戏 HTML 文件在根目录的 /games/ 下
else:
    # 本地开发环境
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
    SEED_DIR = os.path.dirname(__file__)  # 游戏 HTML 文件在 seed/games/ 下

from app.database import async_session, engine, Base
from app.models import User, Game
from app.utils.security import hash_password
from app.utils.s3_client import get_s3_client, ensure_bucket
from app.config import settings

# SEED_DIR defined above (handles Docker vs local)

# ---- 种子数据定义 ----
# 3 款手写 HTML5 小游戏，用于演示平台的浏览/游玩功能
SEED_GAMES = [
    {
        "title": "Classic Snake",
        "description": "Control a growing snake, eat apples, and avoid crashing into yourself. A timeless arcade classic reimagined.",
        "tags": ["arcade", "classic", "snake"],
        "html_file": "snake.html",
    },
    {
        "title": "Memory Match",
        "description": "Flip cards and find matching pairs of cute emojis. Test your memory with 8 pairs to discover.",
        "tags": ["puzzle", "memory", "casual"],
        "html_file": "memory.html",
    },
    {
        "title": "Breakout Blitz",
        "description": "Destroy all the colorful bricks with your ball and paddle. Classic brick-breaker action!",
        "tags": ["arcade", "classic", "breakout"],
        "html_file": "breakout.html",
    },
]


async def clear_existing():
    """清空已有种子数据，确保幂等性（多次运行结果一致）。"""
    async with async_session() as db:
        from sqlalchemy import delete
        await db.execute(delete(Game))   # 先删 Game（因为依赖 User 外键...等等，
        await db.execute(delete(User))   # 实际应该先删 Game 再删 User）
        await db.commit()
    print("Cleared existing data.")


async def create_test_user() -> User:
    """创建测试创作者账户。

    凭据：demo@aigame.dev / demo123
    角色：creator — 可以创建游戏、触发 AI 生成
    """
    async with async_session() as db:
        user = User(
            username="democreator",
            email="demo@aigame.dev",
            password_hash=hash_password("demo123"),
            role="creator",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        print(f"Created test user: {user.username} (demo@aigame.dev / demo123)")
        return user


async def upload_and_create_games(user: User):
    """上传 HTML 游戏到 S3 兼容存储并创建数据库记录。

    流程：
    1. 为每个种子游戏创建 Game 记录 → 获得 UUID
    2. 读取 HTML 文件 → 作为 Body 上传到 S3/MinIO
    3. 设置 game_url 指向后端 play-html API 端点

    关键设计决策：
    - game_url 指向后端 API（/api/games/{id}/play-html）而非 OSS 直链
      原因：OSS 的 Content-Disposition 可能是 attachment，导致浏览器下载而非渲染
           通过后端端点可控制 Content-Disposition: inline，确保 iframe 正常播放
    - object key 格式：games/{uuid}/index.html，结构清晰便于管理
    """
    client = get_s3_client()
    bucket = settings.minio_bucket
    ensure_bucket()  # 确保 bucket 存在（不存在则创建）

    async with async_session() as db:
        for seed in SEED_GAMES:
            # 拼接 HTML 文件路径（适配 Docker 和本地两种环境）
            html_path = os.path.join(SEED_DIR, "games", seed["html_file"])
            if not os.path.exists(html_path):
                print(f"WARNING: Game HTML not found: {html_path}")
                continue

            # ---- 步骤 1: 创建 Game 记录（获得 UUID） ----
            game = Game(
                title=seed["title"],
                description=seed["description"],
                tags=seed["tags"],
                author_id=user.id,
                status="published",      # 种子游戏直接发布
                prompt_text=f"A fun {seed['tags'][0]} game.",
            )
            db.add(game)
            await db.commit()
            await db.refresh(game)       # 刷新以获取服务端生成的 UUID

            # ---- 步骤 2: 上传 HTML 到 S3 兼容存储 ----
            # 【为什么使用 BytesIO 而不是原始 bytes？】
            #   boto3 的 put_object 方法接受 Body 参数为以下类型：
            #     - bytes（原始字节）
            #     - BinaryIO / BytesIO（类文件对象，支持 .read()）
            #     - str（字符串，需指定编码）
            #
            #   使用 BytesIO(html_data) 而不是 html_data（bytes）的原因：
            #     1. boto3 内部使用 requests 库发送 HTTP 请求
            #     2. 对于文件上传，requests 可以接受 bytes，但对于
            #        流式上传（分片上传、大文件），类文件对象更高效
            #     3. BytesIO 提供 .seek() 和 .tell() 方法，boto3 可能
            #        需要这些方法来支持重试或分片
            #     4. 对于包含非 ASCII 字符（中文等）的 HTML，
            #        BytesIO 封装可以确保 Content-Length 计算正确
            #     5. 统一接口：无论数据来源是文件读取还是字符串编码，
            #        都用 BytesIO 包装，代码风格一致
            #
            #   实际上 boto3 put_object 传递 bytes 也是可以的，
            #   但 BytesIO 是更好的实践——它为未来可能的流式上传留有余地
            from io import BytesIO
            oss_key = f"games/{game.id}/index.html"
            with open(html_path, "rb") as f:
                html_data = f.read()

            client.put_object(
                Bucket=bucket,
                Key=oss_key,
                Body=BytesIO(html_data),   # 类文件对象，支持流式传输
                ContentType="text/html",    # 确保浏览器按 HTML 类型解析
                ACL="public-read",          # 公开可读（桶级别也需设置 CORS）
            )

            # ---- 步骤 3: 设置游戏 URL ----
            # 使用后端 API 端点而非 OSS 直链：
            #   好处：后端控制 Content-Disposition: inline
            #         避免 OSS 返回 attachment 导致浏览器下载
            #   play-html 端点：GET /api/games/{id}/play-html
            #     1. 查询 game.game_url 是否指向 OSS
            #     2. 从 OSS 获取 HTML 内容
            #     3. 以 Content-Disposition: inline 返回
            #     4. 若无 OSS，从 DB generation_tasks.llm_response_raw 降级服务
            game.game_url = f"/api/games/{game.id}/play-html"
            await db.commit()

            print(f"Seeded: {game.title} → {game.game_url}")

    print(f"\nSeeded {len(SEED_GAMES)} games successfully!")
    print(f"\nLogin: demo@aigame.dev / demo123")


async def main():
    print("=== AI Game Platform — Seed Script ===\n")

    # 确保数据库表存在（等价于 CREATE TABLE IF NOT EXISTS）
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # 按顺序执行：清空 → 创建用户 → 上传游戏
    await clear_existing()
    user = await create_test_user()
    await upload_and_create_games(user)

    print("\nDone! Start the backend and frontend to see the games.")
    print("  Backend: cd backend && uvicorn app.main:app --reload")
    print("  Frontend: cd frontend && npm run dev")


if __name__ == "__main__":
    asyncio.run(main())
