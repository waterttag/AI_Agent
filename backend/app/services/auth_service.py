"""
认证业务逻辑层 (Authentication Business Logic)
===============================================
WHAT: 封装用户注册、登录、按 ID 查询等核心认证业务逻辑。
WHY:  将业务逻辑从 API 路由层分离出来，遵循"分层架构"(Layered Architecture)：
      Router 层  → 处理 HTTP 请求/响应、参数提取、错误码转换
      Service 层 → 处理业务规则（唯一性检查、密码验证）、数据持久化
      这样 Router 保持简洁，Service 可以独立测试、被多个 Router 复用。

架构收益:
    1. 可测试性: Service 函数可以直接用 pytest 单元测试，不需要启动 FastAPI
    2. 可复用: 如果将来需要 CLI 工具或 GraphQL 接口，直接调用 service 即可
    3. 可维护: 业务规则变更时只改 service，Router 层不受影响
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.schemas.user import UserCreate, UserResponse, TokenResponse

# 安全工具: 密码哈希/验证、JWT 创建
from app.utils.security import hash_password, verify_password, create_access_token


# ============================================================================
# AuthError — 自定义认证异常
# ============================================================================
class AuthError(Exception):
    """
    认证失败的异常类。

    设计目的:
        - 统一认证错误类型，Router 层可以 catch AuthError 并转换为合适的 HTTP 状态码
        - 比直接 raise HTTPException 更好：Service 层不应依赖 FastAPI（保持框架无关）
        - Router 层负责"将业务错误映射到 HTTP 协议"，Service 层只关心"是什么业务错误"

    使用示例:
        # Service 层
        raise AuthError("Email already registered")
        raise AuthError("Invalid email or password")

        # Router 层
        try:
            return await register_user(...)
        except AuthError as e:
            raise HTTPException(status_code=409, detail=str(e))
    """
    pass


# ============================================================================
# register_user — 用户注册
# ============================================================================
async def register_user(db: AsyncSession, data: UserCreate) -> TokenResponse:
    """
    注册新用户并返回 JWT 访问令牌。

    业务流程:
        1. 检查邮箱唯一性（SELECT ... WHERE email = ?）
        2. 检查用户名唯一性（SELECT ... WHERE username = ?）
        3. bcrypt 哈希密码（不存储明文）
        4. 创建用户记录（默认 role="creator"）
        5. 签发 JWT token
        6. 返回 TokenResponse（token + 用户信息）

    为什么先查邮箱再查用户名？
        - 两个检查是独立的，顺序不影响结果
        - 但先检查邮箱更好，因为登录使用的是邮箱（而非用户名），邮箱重复冲突更重要

    为什么使用 bcrypt 哈希密码？
        - bcrypt 是专门为密码存储设计的哈希算法（基于 Blowfish 加密算法）
        - 自带 salt（随机盐）：每个密码的哈希结果不同，即使相同密码也产生不同哈希
        - 慢哈希（computationally expensive）：通过 cost factor 控制计算量，抵抗暴力破解
        - 不同于 SHA-256 等通用哈希，bcrypt 故意慢，使得 GPU 批量破解不经济
        - 本项目中通过 passlib 库的 CryptContext 使用 bcrypt

    为什么默认 role="creator"？
        - 本平台角色设计: admin（管理员）vs creator（创作者/普通用户）
        - 公共注册的用户都是 creator，admin 需要手动指定（通过数据库或 seed 脚本）
        - 这遵循"最小权限原则"：新用户默认只有基础权限
    """
    # ---- 唯一性检查1: 邮箱 ----
    # scalar_one_or_none(): 最多返回一条记录，无结果返回 None，多条抛异常（理论上不会，因为有唯一索引）
    result = await db.execute(select(User).where(User.email == data.email))
    if result.scalar_one_or_none():
        raise AuthError("Email already registered")

    # ---- 唯一性检查2: 用户名 ----
    # 注意: 即使数据库有 UNIQUE 约束，这里也在应用层做一次检查，
    # 因为: 1) 可以给出更友好的错误消息 2) 避免依赖数据库异常的字符串解析
    result = await db.execute(select(User).where(User.username == data.username))
    if result.scalar_one_or_none():
        raise AuthError("Username already taken")

    # ---- 创建用户 ----
    # password_hash: 存储的是 bcrypt 哈希结果，不是明文密码
    # hash_password 内部生成随机 salt 并执行多轮 Blowfish 加密
    user = User(
        username=data.username,
        email=data.email,
        password_hash=hash_password(data.password),
        role="creator",
    )
    db.add(user)       # 加入 session 的待提交队列
    await db.commit()  # 写入数据库（此时 user.id 已生成）
    await db.refresh(user)  # 刷新对象状态，确保有完整的数据库返回字段（如 created_at）

    # ---- 签发 JWT ----
    # payload 中的 "sub" 是 JWT 标准注册声明 (RFC 7519 Section 4.1.2)
    # 表示 token 的主题 — 这里就是用户的唯一 ID
    token = create_access_token({"sub": user.id})

    # ---- 组装响应 ----
    # TokenResponse 结构: { access_token: "...", token_type: "bearer", user: {...} }
    return TokenResponse(
        access_token=token,
        user=UserResponse.model_validate(user),
    )


# ============================================================================
# login_user — 用户登录
# ============================================================================
async def login_user(db: AsyncSession, email: str, password: str) -> TokenResponse:
    """
    验证用户凭据并返回 JWT 访问令牌。

    业务流程:
        1. 按邮箱查找用户
        2. bcrypt 验证密码
        3. 签发 JWT token
        4. 返回 TokenResponse

    安全考虑:
        - 错误消息统一: 无论"邮箱不存在"还是"密码错误"都返回 "Invalid email or password"
          这是防止用户枚举攻击 (User Enumeration Attack)
          攻击者无法通过错误消息的差异判断某个邮箱是否已注册
        - 没有登录失败计数: 当前未实现暴力破解防护
          生产环境应添加: rate limiting（N 次/分钟/IP）、账户临时锁定、CAPTCHA 验证

    性能考虑:
        - bcrypt.verify 是 CPU 密集型操作（设计如此），每次约 200-500ms
        - 在异步上下文中它不是 async 函数，会阻塞事件循环线程
        - 对于低并发场景没问题，高并发下可考虑:
          1. 将 bcrypt 操作放到线程池（run_in_executor）
          2. 使用更快的密码哈希方案（如 argon2id 的优化实现）
          3. 添加登录频率限制来限制攻击面
    """
    # ---- 步骤1: 按邮箱查找用户 ----
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    # ---- 步骤2: 验证密码 ----
    # verify_password 内部流程:
    # 1. 从存储的哈希中提取 salt（bcrypt 哈希格式: $2b$12$<salt><hash>）
    # 2. 用相同的 salt 和 cost factor 对明文进行哈希
    # 3. 比较两个哈希是否一致（恒定时间比较，防时序攻击）
    # 如果用户不存在，or 短路不会执行 verify_password（避免对不存在用户做 CPU 密集型操作）
    if not user or not verify_password(password, user.password_hash):
        raise AuthError("Invalid email or password")

    # ---- 步骤3: 签发 JWT ----
    token = create_access_token({"sub": user.id})

    # ---- 步骤4: 返回 ----
    return TokenResponse(
        access_token=token,
        user=UserResponse.model_validate(user),
    )


# ============================================================================
# get_user_by_id — 按 ID 查询用户
# ============================================================================
async def get_user_by_id(db: AsyncSession, user_id: str) -> User | None:
    """
    通过用户 ID 获取 User ORM 对象。

    这是一个轻量级的查询函数，被 get_current_user 依赖调用。
    返回 None 表示用户不存在（可能已被删除）。

    为什么单独封装一个函数而不是在 deps.py 中直接写 SQL？
        1. 复用: 多个地方需要按 ID 查用户
        2. 一致性: 所有用户查询通过统一的 service 层
        3. 可测试: 可以 mock 这个函数来测试依赖注入逻辑
    """
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()
