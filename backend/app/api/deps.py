"""
FastAPI 依赖注入模块 (Dependency Injection)
============================================
WHAT: 提供两个核心依赖函数 — get_current_user（强制认证，401）和 get_optional_user（可选认证，不报错）。
WHY:  将认证逻辑从路由处理函数中抽离，通过 FastAPI 的 Depends 机制复用。
      路由函数只需声明 `current_user: User = Depends(get_current_user)` 即可获得当前用户对象，
      无需在每个端点中重复解析 token、查询数据库的代码。
技术知识: FastAPI 的依赖注入系统类似于 pytest fixture — 可以嵌套、可以被缓存、
        可以在请求级别共享（同一个请求中多次 Depends 同一个依赖只会执行一次）。

关键设计决策:
- HTTPBearer(auto_error=False): 不自动报错，由依赖函数自行决定是否返回 401。
- 两个依赖函数复用同一个 security 实例，避免重复创建 HTTPBearer 对象。
"""

from fastapi import Depends, HTTPException, status
# HTTPBearer: FastAPI 内置的 Bearer Token 提取器。
# 它从请求头 `Authorization: Bearer <token>` 中提取 token 字符串。
# HTTPAuthorizationCredentials: 包含 scheme（"Bearer"）和 credentials（token 字符串）两个字段。
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

# SQLAlchemy 异步 session 类型注解
from sqlalchemy.ext.asyncio import AsyncSession

# 数据库 session 工厂的依赖函数（定义在 database.py 中）
from app.database import get_db

# JWT 解码函数（验证签名 + 过期时间，返回 payload 字典或 None）
from app.utils.security import decode_access_token

# 通过用户 ID 查询 User ORM 对象的服务层函数
from app.services.auth_service import get_user_by_id


# ============================================================================
# HTTPBearer 实例 — 全局单例
# ============================================================================
# auto_error=False 的含义:
#   - True (默认):  如果请求中没有 Authorization 头或格式不对，HTTPBearer 直接抛出 401，
#                   请求根本不会进入你的依赖函数。适用于"必须登录"的端点。
#   - False:        不自动报错，而是将 credentials 参数设为 None 传给依赖函数，
#                   由依赖函数自行决定如何处理未认证请求。
#                   这里设为 False 是因为我们需要同时支持 get_current_user（必须登录）
#                   和 get_optional_user（可选登录），两者共用一个 HTTPBearer 实例。
#                   如果设为 True，get_optional_user 就永远收不到未认证的请求了。
security = HTTPBearer(auto_error=False)


# ============================================================================
# get_current_user — 强制认证依赖
# ============================================================================
async def get_current_user(
    # 【参数1】HTTP 认证凭证，由 HTTPBearer 从请求头中提取。
    # Depends(security) 告诉 FastAPI: "请先执行 security 对象来获取这个参数的值"。
    # 由于 auto_error=False，未认证时 credentials 为 None，不会提前抛异常。
    credentials: HTTPAuthorizationCredentials | None = Depends(security),

    # 【参数2】数据库异步 session，由 get_db 依赖提供。
    # FastAPI 会在请求结束时自动关闭这个 session（通过 yield 机制）。
    db: AsyncSession = Depends(get_db),
):
    """
    依赖函数: 从 Bearer Token 中提取并验证当前用户。

    返回值: User ORM 对象（SQLAlchemy 模型实例）
    异常:   HTTPException(401) — token 缺失 / token 无效或过期 / 用户不存在

    使用方式:
        @router.get("/me")
        async def profile(current_user: User = Depends(get_current_user)):
            return {"username": current_user.username}
    """

    # --- 步骤1: 检查 token 是否存在 ---
    # 如果 HTTPBearer 没有提取到 token（请求头缺失或格式错误），直接返回 401。
    # WWW-Authenticate 头是 HTTP 标准要求 — 告诉客户端"你应该用 Bearer 方式认证"。
    # 浏览器在看到这个头 + 401 状态码时会弹出登录框，API 客户端通常忽略它。
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # --- 步骤2: 解码并验证 JWT ---
    # decode_access_token 内部做了两件事:
    #   1. 验证签名: 用 settings.jwt_secret 重新计算 HMAC，与 token 中的签名比对，
    #      如果被篡改或密钥不匹配 → 返回 None
    #   2. 验证过期: 检查 exp 字段是否已过当前 UTC 时间 → 返回 None
    # credentials.credentials 是去掉 "Bearer " 前缀后的纯 token 字符串。
    payload = decode_access_token(credentials.credentials)

    # 如果解码失败（签名错/过期/格式错），payload 为 None 或缺少 sub 字段 → 401
    # "sub" 是 JWT RFC 7519 标准注册声明，代表"主题"(Subject)，
    # 这里我们存的是用户的唯一 ID。
    if not payload or "sub" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    # --- 步骤3: 从数据库加载用户 ---
    # 即使 token 有效，也要确认用户仍然存在（可能已被管理员删除）。
    # 这里没有做"token 是否被撤销"的检查（本项目无 token 黑名单），
    # 如需登出功能则需要引入 Redis 黑名单或使用短过期时间。
    user_id = payload["sub"]
    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    # 返回 ORM 对象，路由函数可以直接访问 user.id、user.username 等属性。
    # 注意: 返回的是 SQLAlchemy 管理的对象，如果路由函数中访问未 eager-load 的关系
    #       会触发懒加载，在异步上下文中可能导致 greenlet 错误。
    #       解决方案: 在查询时使用 selectinload() 预加载需要的关联数据。
    return user


# ============================================================================
# get_optional_user — 可选认证依赖
# ============================================================================
async def get_optional_user(
    # 参数和 get_current_user 完全一样，共享同一个 HTTPBearer 实例
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
):
    """
    依赖函数: 尝试提取当前用户，但不强制要求登录。

    返回值: User ORM 对象 或 None（未认证时）
    不抛出异常 — 这是与 get_current_user 唯一的行为差异。

    使用场景: 某些端点需要对登录用户和匿名用户展示不同内容，但两种用户都应该能访问。
    例如: 游戏列表页 — 登录用户看到自己的收藏状态，匿名用户只看公开数据。
          路由函数通过 `if current_user:` 来区分处理逻辑。
    """
    # 未认证 → 返回 None，路由函数自行处理匿名逻辑
    if not credentials:
        return None

    # token 无效 → 同样返回 None，不给匿名用户报错
    payload = decode_access_token(credentials.credentials)
    if not payload or "sub" not in payload:
        return None

    # 用户可能已被删除 → 同样静默返回 None
    return await get_user_by_id(db, payload["sub"])
