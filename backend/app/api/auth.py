"""
认证 API 路由 (Authentication API Routes)
==========================================
WHAT: 提供用户注册、登录、获取个人信息、获取收藏游戏 ID 列表的 REST 端点。
WHY:  认证是平台的入口功能，独立为一个路由模块便于维护和版本管理。
      登录/注册返回 JWT token + 用户信息，前端存储 token 后每次请求通过 Authorization 头携带。
技术知识: RESTful 设计 — POST 用于创建资源（注册）、POST 用于认证操作（登录，因为不是幂等的）、
         GET 用于读取资源（/me、/me/favorites）。收藏 ID 列表放在 /auth/me/favorites 而非 /games 下，
         是为了避免与 /games/{game_id} 的路径参数冲突（详见 games.py 末行注释说明）。
"""

from fastapi import APIRouter, Depends, HTTPException, status

# SQLAlchemy 的 select 函数 — 用于构建类型安全的 SELECT 查询
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# 数据库 session 依赖
from app.database import get_db

# Pydantic schema — 数据验证和序列化
# UserCreate:  注册请求体 {username, email, password}
# UserLogin:   登录请求体 {email, password}
# UserResponse: 用户信息响应体（不含密码哈希）
# TokenResponse: 登录/注册成功响应 {access_token, token_type, user}
from app.schemas.user import UserCreate, UserLogin, UserResponse, TokenResponse

# GameResponse — 虽然目前未直接在此文件使用，但保留导入以便后续扩展（如注册后自动创建示例游戏）
from app.schemas.game import GameResponse

# 服务层 — 封装了业务逻辑（密码哈希、JWT 生成）
from app.services.auth_service import register_user, login_user, AuthError

# 依赖注入 — get_current_user 确保只有登录用户能访问 /me 和 /me/favorites
from app.api.deps import get_current_user

# ORM 模型 — 用于直接查询数据库（/me/favorites 是一个简单查询，直接写比加 service 函数更轻量）
from app.models.user import User
from app.models.game import GameFavorite, Game


# 创建路由实例，所有端点路径都相对于 /api/auth（因为顶层 api_router 有 /api 前缀）
router = APIRouter(prefix="/auth", tags=["Auth"])


# ============================================================================
# POST /api/auth/register — 用户注册
# ============================================================================
@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(data: UserCreate, db: AsyncSession = Depends(get_db)):
    """
    注册新用户账号。

    请求体 (UserCreate):
        - username: 用户名（唯一）
        - email:    邮箱（唯一）
        - password: 明文密码（服务端立即 bcrypt 哈希，不存储明文）

    响应 (TokenResponse, 201):
        - access_token: JWT token，前端存入 localStorage/sessionStorage
        - token_type:   "bearer"
        - user:         UserResponse（id, username, email, role, created_at）

    错误:
        - 409 Conflict: 邮箱或用户名已存在

    设计决策:
        - 注册即登录: 直接返回 token，避免用户注册后还要再调 /login，减少一次网络请求。
        - 201 Created: REST 语义 — 创建了新资源（用户）。
        - password 不在响应中: Pydantic schema 排除了 password_hash 字段，确保安全。
    """
    try:
        # register_user 服务层函数会做邮箱/用户名唯一性检查 + bcrypt 哈希 + JWT 签发
        return await register_user(db, data)
    except AuthError as e:
        # AuthError 是 auth_service.py 中定义的自定义异常，
        # 这里转换为 HTTP 409（Conflict），语义更精确 — 资源冲突（重复注册）
        # 而不是笼统的 400 Bad Request
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


# ============================================================================
# POST /api/auth/login — 用户登录
# ============================================================================
@router.post("/login", response_model=TokenResponse)
async def login(data: UserLogin, db: AsyncSession = Depends(get_db)):
    """
    使用邮箱和密码登录。

    请求体 (UserLogin):
        - email:    邮箱
        - password: 明文密码

    响应 (TokenResponse, 200):
        - 和注册一样，返回 JWT token + 用户信息

    错误:
        - 401 Unauthorized: 邮箱不存在或密码错误

    安全考虑:
        - 错误消息统一为 "Invalid email or password"，不区分是"邮箱不存在"还是"密码错误"，
          防止攻击者通过错误消息差异枚举已注册邮箱（用户枚举攻击）。
        - 没有做登录失败次数限制 — 生产环境应加入 rate limiting 或账户锁定机制。
    """
    try:
        # login_user 先按邮箱查用户，再 bcrypt.verify 比对密码
        return await login_user(db, data.email, data.password)
    except AuthError as e:
        # 登录失败返回 401（而非 400 或 409），因为这是认证失败
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


# ============================================================================
# GET /api/auth/me — 获取当前用户信息
# ============================================================================
@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """
    获取当前认证用户的个人信息。

    认证: 必须携带有效的 Bearer token（由 get_current_user 依赖确保）。

    响应 (UserResponse, 200):
        - id, username, email, role, created_at（不含 password_hash）

    实现细节:
        - model_validate 是 Pydantic v2 的方法（v1 是 from_orm），
          将 SQLAlchemy ORM 对象转换为 Pydantic schema 实例。
        - 由于 UserResponse 只定义了部分字段，model_validate 会自动忽略 ORM 中多余的字段
          （如 password_hash），这是一种隐式的字段白名单机制。
    """
    return UserResponse.model_validate(current_user)


# ============================================================================
# GET /api/auth/me/favorites — 获取当前用户的收藏游戏 ID 列表
# ============================================================================
@router.get("/me/favorites", response_model=list[str])
async def get_my_favorite_ids(
    current_user: User = Depends(get_current_user),   # 谁在请求
    db: AsyncSession = Depends(get_db),               # 数据库连接
):
    """
    获取当前用户收藏的所有游戏的 ID 列表。

    返回: JSON 字符串数组，如 ["game-uuid-1", "game-uuid-2"]

    为什么返回 ID 列表而不是完整的 Game 对象？
        - 前端通常已经有游戏列表数据（从 /api/games 获取），
          只需要知道哪些 ID 被收藏了，前端自行高亮收藏按钮即可。
        - 减少响应体积: ID 列表远小于完整游戏对象数组。
        - 避免重复查询: 前端不需要因为收藏状态变化而重新拉取所有游戏详情。

    为什么这个端点放在 /auth/me/ 下而不是 /games/ 下？
        关键原因: /api/games/{game_id} 已经占用了路径参数，
        如果定义 GET /api/games/favorites，FastAPI 会把 "favorites" 当作 game_id 值，
        导致路由冲突（除非使用路由优先级，但这会增加维护复杂度）。
        FastAPI 按定义顺序匹配路由，静态路径需要写在动态路径前面，
        但更稳妥的做法是把用户专属的收藏列表放在 /auth/me 下。
    """
    # 只查询 game_id 列（而非整个 GameFavorite 对象），减少数据传输
    # select(GameFavorite.game_id) 生成的 SQL: SELECT game_favorites.game_id FROM game_favorites WHERE ...
    result = await db.execute(
        select(GameFavorite.game_id).where(GameFavorite.user_id == current_user.id)
    )

    # result.all() 返回 [(game_id1,), (game_id2,), ...] — 单列元组列表
    # 用列表推导式提取每行的第一个（也是唯一的）元素，得到纯字符串列表
    return [row[0] for row in result.all()]
