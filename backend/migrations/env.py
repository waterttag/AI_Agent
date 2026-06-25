# ============================================================
# Alembic 迁移环境配置 — Async SQLAlchemy 支持
# ============================================================
# 功能：为 Alembic 提供 async 数据库引擎的执行环境
#
# 核心挑战：Alembic 原生是同步的，但本项目使用
# SQLAlchemy 异步引擎（create_async_engine + async_session）。
# 本文件通过 run_sync() 桥接同步/异步两个世界。
#
# 执行流程：
#   alembic upgrade head
#     → context.is_offline_mode()? → run_migrations_offline()  (生成 SQL 文件)
#                                → run_migrations_online()    (直接执行)
#       → asyncio.run(run_async_migrations())
#         → create_async_engine(url)
#         → connection.run_sync(do_run_migrations)  # 关键桥接点
#
# 两种模式：
#   1. offline 模式（--sql）：生成 SQL 文本而不执行（用于审查/手动部署）
#   2. online 模式（默认）：直接在数据库上执行迁移
# ============================================================

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

# ---- 导入模型元数据 ----
# Base.metadata 包含所有 ORM 模型的结构信息
# Alembic 的 --autogenerate 功能通过对比 metadata 和数据库现状
# 自动生成差异迁移脚本
from app.database import Base

# 显式导入所有模型，确保它们被 SQLAlchemy 注册到 Base.metadata
# # noqa 注释：告诉 linter（如 flake8）忽略"未使用导入"警告
# 这些导入虽然看似未使用，但执行了模型类的声明式注册
from app.models import User, Game, GameAsset, GenerationTask  # noqa: ensure models loaded
from app.config import settings

# ---- 加载 Alembic 配置 ----
# config 是 Alembic 的全局配置对象
# 它读取 alembic.ini 文件中的 [alembic] 段
config = context.config

# fileConfig: 加载 alembic.ini 中的 [loggers]/[handlers]/[formatters] 配置
# 这使得迁移过程中的日志输出符合预期格式（见 alembic.ini 注释）
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 设置 Alembic 比较的目标元数据
# autogenerate 会对比 target_metadata 和数据库实际表结构
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """离线模式：生成 SQL 语句文本而非直接执行。

    使用场景：
    - 生产环境 DBA 审核迁移 SQL 后再手动执行
    - CI/CD 中生成 SQL 作为制品输出
    - 学习 Alembic 会生成什么 SQL 语句

    参数说明：
    - url: 数据库连接字符串（从 settings 动态获取，覆盖 ini 文件中的配置）
    - target_metadata: ORM 模型元数据
    - literal_binds: True 表示将 Python 值转换为 SQL 字面量
      （例如 datetime.now() → "2024-01-01 12:00:00"）
    - dialect_opts: 方言选项，paramstyle="named" 使用 :name 占位符
    """
    context.configure(
        url=settings.get_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    # begin_transaction() 创建一个事务上下文
    # 在上下文中运行迁移（生成 SQL 文本）
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    """在已有数据库连接上运行迁移（同步包装器）。

    此函数被 run_sync() 调用，运行在同步上下文中。
    connection 是由 create_async_engine 提供的协程安全连接
    通过 run_sync() 转换为同步连接。

    参数：
    - connection: 同步数据库连接（由 run_sync 桥接）
    """
    context.configure(
        connection=connection,           # 使用已有连接（而非创建新连接）
        target_metadata=target_metadata,
    )

    # 在事务中运行迁移
    # 如果任何迁移步骤失败，整个事务回滚
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """在线模式：使用异步引擎直接执行迁移。

    这是默认模式下的核心函数。
    流程：
    1. 创建异步数据库引擎（从 settings 获取 URL）
    2. 通过 connect() 获取异步连接
    3. 通过 run_sync() 桥接：在异步事件循环中运行同步代码
       run_sync 将异步连接包装为同步连接，允许调用
       Alembic 的同步 API（do_run_migrations）
    4. dispose() 释放引擎资源（连接池等）
    """
    # 创建异步引擎
    # settings.get_database_url() 根据环境变量返回正确的数据库 URL
    # 例如：sqlite+aiosqlite:///./app.db（开发）或 postgresql+asyncpg://...（生产）
    connectable = create_async_engine(settings.get_database_url())

    async with connectable.connect() as connection:
        # 【关键桥接点】run_sync 是 async 到 sync 的桥梁
        # 它将 do_run_migrations 放在当前事件循环中执行
        # do_run_migrations 内部使用 connection 的同步包装器
        # 这意味着 Alembic 的同步迁移 API 可以在 async 引擎上运行
        await connection.run_sync(do_run_migrations)

    # 释放引擎：关闭所有连接，清理连接池
    await connectable.dispose()


def run_migrations_online() -> None:
    """在线模式入口：启动异步事件循环执行迁移。

    因为 Alembic 的顶层调用是同步的（context 期望同步函数），
    这里用 asyncio.run() 启动新的事件循环来运行异步迁移。

    asyncio.run():
    - 创建新的事件循环
    - 运行 run_async_migrations() 直到完成
    - 关闭事件循环
    - 只应在主线程中调用一次
    """
    asyncio.run(run_async_migrations())


# ---- 判断运行模式 ----
# context.is_offline_mode() 检查是否使用了 --sql 参数
# 如果是，生成 SQL 文本而不连接数据库
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
