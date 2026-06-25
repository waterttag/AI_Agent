"""Async SQLAlchemy engine and session management.

基于 SQLAlchemy 2.0 异步引擎的数据库连接管理模块。
核心职责：
1. 创建异步数据库引擎（支持 SQLite 和 PostgreSQL）
2. 提供异步会话工厂（async_sessionmaker）
3. 定义 ORM 基类（DeclarativeBase）
4. 提供 FastAPI 依赖注入函数（get_db）
"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.config import settings

# 在模块加载时调用 get_database_url() 以确定数据库 URL。
# 此函数会根据配置和运行环境自动选择 SQLite 或 PostgreSQL，
# 具体逻辑见 config.py 中的实现。
_db_url = settings.get_database_url()

# [SQLite 特殊处理：check_same_thread]
# SQLite 默认只允许创建连接的线程访问数据库（check_same_thread=True），
# 这是为了防止多线程并发写入导致的数据损坏。
# 但在异步 SQLAlchemy 中，连接可能在不同线程间传递（通过 greenlet/协程调度），
# 因此必须设置 check_same_thread=False 来禁用此检查。
#
# 技术背景：
#   - greenlet 是一种轻量级协程实现，SQLAlchemy 异步扩展使用它来实现
#     "同步风格的代码在异步上下文中执行"——当你 await 一个数据库操作时，
#     底层实际是在一个 greenlet 中执行同步的 SQLAlchemy 代码。
#   - greenlet 切换时，操作系统线程不会改变，但在某些边缘场景下
#     (如使用 run_in_executor) 可能跨越线程，所以需要 check_same_thread=False。
#   - SQLite 在多线程环境下的安全性由 WAL 模式（Write-Ahead Logging）保证，
#     这是通过 SQLAlchemy 连接事件自动启用的。
_connect_args = {"check_same_thread": False} if "sqlite" in _db_url else {}

# [连接池策略：NullPool vs QueuePool]
# SQLite 不支持网络并发连接，它本质上是一个文件锁机制。
# 使用默认的 QueuePool（连接池）在 SQLite 场景下会导致问题：
#   - 多个连接同时写入可能触发 "database is locked" 错误
#   - 连接池中的连接可能在不同线程间复用，与 SQLite 的线程模型冲突
#
# 因此 SQLite 使用 NullPool：
#   - NullPool 不维护任何连接池，每次操作都创建新连接
#   - 配合 aiosqlite 异步驱动，每次数据库操作都是独立的
#   - 虽然创建连接有一定开销，但对 SQLite（本地文件）来说微不足道
#
# PostgreSQL 使用默认的 QueuePool（当 poolclass=None 时）：
#   - QueuePool 维护一定数量的持久连接（默认 5 个连接 + 10 个溢出）
#   - 避免了频繁创建/销毁 TCP 连接的开销
#   - 适合高并发 Web 应用的场景
_poolclass = NullPool if "sqlite" in _db_url else None

# 创建异步数据库引擎。
# create_async_engine 返回 AsyncEngine 实例，它是整个应用数据库操作的核心。
# 参数说明：
#   - echo=False:  不打印 SQL 语句到控制台（生产环境设为 False，调试时可改为 True）
#   - connect_args: 传递给底层 DBAPI 驱动的连接参数
#   - poolclass:   连接池策略类，None 使用默认（QueuePool）
engine = create_async_engine(
    _db_url,
    echo=False,
    connect_args=_connect_args,
    poolclass=_poolclass,
)

# async_sessionmaker 是一个可调用对象（工厂函数），每次调用创建新的 AsyncSession。
# 参数说明：
#   - class_=AsyncSession: 指定会话类型为异步会话
#   - expire_on_commit=False: 提交后不过期已加载的对象。
#     设为 False 的原因：在 FastAPI 依赖注入模式中，
#     会话在请求结束后关闭，如果对象在提交后被过期，
#     那么在响应序列化时访问对象属性会触发额外的数据库查询（懒加载），
#     而此时会话通常已经关闭，会抛出 DetachedInstanceError。
#     设为 False 后，对象在提交后仍然可以正常访问属性，避免了此问题。
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    """所有 ORM 模型类的基类。

    所有数据库表对应的模型类必须继承 Base，例如：
        class User(Base):
            __tablename__ = "users"
            ...

    DeclarativeBase 是 SQLAlchemy 2.0 的新式声明基类，
    替代了旧版的 declarative_base() 函数。
    通过继承此类，模型会自动获得：
    - 表名自动生成（基于类名）
    - 列类型推断
    - 关系映射支持
    - Metadata 对象（存储所有表定义）
    """
    pass


async def get_db() -> AsyncSession:
    """FastAPI 依赖注入函数：为每个请求提供一个异步数据库会话。

    使用模式（在 FastAPI 路由中）：
        @router.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db)):
            result = await db.execute(select(Item))
            return result.scalars().all()

    工作原理：
    1. FastAPI 调用此函数创建 AsyncSession
    2. yield 将 session 交给路由处理函数使用
    3. 路由处理完成后，finally 块确保 session 被关闭

    为什么用 try/finally 而不是 async with：
        FastAPI 的 Depends 机制在生成器退出时执行 finally 块。
        使用 yield 而不是 return + async with 是因为：
        - yield 可以跨越 async with 的上下文管理器边界
        - 生成器的 finally 在请求结束后（包括异常）一定执行
        - 确保无论如何数据库连接都会被归还/关闭，避免连接泄漏

    关于 session.close() 的必要性：
        - 对于 NullPool（SQLite），close() 直接关闭底层连接
        - 对于 QueuePool（PostgreSQL），close() 将连接归还给连接池
        - 不关闭会导致连接泄漏，最终耗尽连接池
    """
    async with async_session() as session:
        try:
            yield session
        finally:
            # 确保在任何情况下（包括路由抛出异常）都关闭会话。
            # 这行在 async with 退出后自动执行，额外显式调用是防御性编程。
            await session.close()
