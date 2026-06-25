"""
User-related Pydantic schemas.

用户相关的 Pydantic 数据验证模型（Schema）。

Pydantic 在此承担三重角色：
1. 请求体验证：自动校验输入数据格式、长度、类型
2. 序列化/反序列化：ORM 对象 ↔ JSON 的双向转换
3. API 文档：FastAPI 自动从 Pydantic 模型生成 OpenAPI/Swagger 文档
"""
# =============================================================================
# 用户 Schema 模块
# =============================================================================
# 本模块定义了用户注册、登录、响应和令牌的完整数据契约。
#
# 设计要点：
# - 明文密码仅存在于 UserCreate/UserLogin（输入），绝不出现在响应中
# - Password 字段不设复杂正则（如必须有大小写+数字），避免过严的规则
#   降低用户注册门槛，安全由 bcrypt 哈希保证
# - Field(...) 中的 ... 是 Pydantic 的必需字段标记（等价于 required=True）
# - EmailStr 是 pydantic 的扩展类型，基于 email-validator 库做 RFC 合规校验
# - model_config = {"from_attributes": True} 开启 ORM 模式，
#   允许从 SQLAlchemy ORM 对象直接构造 Pydantic 模型（之前叫 orm_mode）

from datetime import datetime
from pydantic import BaseModel, EmailStr, Field


# =============================================================================
# UserCreate - 用户注册请求体
# =============================================================================
class UserCreate(BaseModel):
    """
    用户注册时的请求体 Schema。

    所有字段都是必需的（...），服务端验证数据的基本合法性。
    """
    # ---- 用户名 ----
    # min_length=3：防止过短的用户名，保证可辨识性
    # max_length=50：与数据库列 String(50) 对齐，减少存储开销
    # 不使用 EmailStr：用户名是显示名称，不是邮箱地址
    username: str = Field(..., min_length=3, max_length=50)
    # ---- 邮箱 ----
    # 使用 str 而非 EmailStr：
    #   这里仅做长度限制，详细的邮箱格式校验由业务层或
    #   依赖的 email-validator 库处理（如果需要严格校验可改为 EmailStr）
    #   某些场景下放宽校验（如测试邮箱）更灵活
    email: str = Field(..., max_length=255)
    # ---- 密码 ----
    # min_length=6：最低安全要求，避免过短密码
    # max_length=128：bcrypt 哈希前对输入没有严格限制，但 128 足够容纳
    #   绝大多数密码（包括密码管理器生成的超长随机密码）
    # 注意：密码在此不做复杂度校验（数字+符号等），
    #   因为复杂的规则通常让用户体验变差，安全性由 bcrypt（慢哈希+加盐）保证
    password: str = Field(..., min_length=6, max_length=128)


# =============================================================================
# UserLogin - 用户登录请求体
# =============================================================================
class UserLogin(BaseModel):
    """
    用户登录时的请求体 Schema。

    与 UserCreate 的区别：
    - 不需要 username：登录凭据是邮箱+密码
    - 密码无 min_length 限制：因为修改密码不需要重新输入，重点是匹配
      （实际校验在业务层：查数据库、bcrypt 比对）
    """
    # ---- 登录邮箱 ----
    # 与注册时相同的字段约束，保持一致性
    email: str = Field(..., max_length=255)
    # ---- 登录密码 ----
    # 不设 min_length 因为业务层已经存储了哈希，此处只是传输明文
    password: str = Field(..., max_length=128)


# =============================================================================
# UserResponse - 用户信息响应体
# =============================================================================
class UserResponse(BaseModel):
    """
    用户信息 API 响应 Schema。

    核心安全原则：绝不包含 password_hash 字段。
    即使数据库有此列，Pydantic 也不会序列化它（因为这里没有声明）。
    这是"最小权限"原则在 API 层的体现。
    """
    # ---- 用户 ID ----
    # 返回 UUID 字符串，前端用它做后续请求（如获取用户游戏列表）
    id: str
    # ---- 用户名 ----
    username: str
    # ---- 邮箱 ----
    # 仅在用户自己的资料页返回邮箱，其他场景由业务层控制
    email: str
    # ---- 角色 ----
    # 前端根据 role 控制 UI 展示（如是否显示管理后台入口）
    role: str
    # ---- 注册时间 ----
    # 前端用于展示"加入于 XXXX 年 XX 月"
    created_at: datetime

    # ---- ORM 兼容模式 ----
    # from_attributes=True（Pydantic v2 语法，v1 称为 orm_mode=True）：
    # 允许直接从 SQLAlchemy ORM 对象构造：
    #   user = db.query(User).first()
    #   return UserResponse.model_validate(user)  # 自动映射
    # 背后的原理：Pydantic 会通过 getattr 访问 ORM 对象的属性，
    #   而不是要求传入字典。这使得序列化层与 ORM 层无缝衔接
    model_config = {"from_attributes": True}


# =============================================================================
# TokenResponse - JWT 令牌响应体
# =============================================================================
class TokenResponse(BaseModel):
    """
    登录成功后的令牌响应 Schema。

    遵循 OAuth 2.0 Bearer Token 规范（简化版）。
    """
    # ---- 访问令牌 ----
    # 前端将 Header: Authorization: Bearer {access_token} 发送给后端
    # 通常为 JWT 格式：header.payload.signature 三段 Base64URL 编码
    # JWT 的优势：
    #   - 无状态：服务端无需存储 session，只需验签
    #   - 可携带声明（claims）：user_id、role、exp 等嵌入在 payload 中
    #   - 跨服务：微服务间共享同一个 JWT 公钥即可独立验证
    access_token: str
    # ---- 令牌类型 ----
    # 固定为 "bearer"，遵循 RFC 6750
    # 前端从 OAuth2 响应中知道如何使用令牌（Bearer 即放在 Authorization 头）
    token_type: str = "bearer"
    # ---- 用户信息 ----
    # 登录成功时一并返回用户基本信息，避免前端再做一次 /me 请求
    # 减少网络往返（RTT），提升用户体验
    user: UserResponse
