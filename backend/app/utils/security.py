"""
安全工具模块 (Password Hashing and JWT Utilities)
===================================================
WHAT: 提供密码 bcrypt 哈希/验证和 JWT token 的创建/解码功能。
WHY:  安全相关的工具独立为一个模块，确保一致性（整个应用用相同的哈希参数和 JWT 配置）。

技术选型:

1. bcrypt 密码哈希:
   - 算法: 基于 Blowfish 加密算法，专为密码存储设计
   - 自带 salt: 每次哈希自动生成随机 salt（16 字节），相同密码产生不同哈希
   - 慢哈希: cost factor（rounds）控制计算量，默认 12 轮（2^12 次迭代）
   - 不可逆: 只有 hash 和 verify，没有 decrypt（与 AES 等加密算法不同）
   - 抗 GPU 破解: bcrypt 设计时需要大量内存访问，GPU 并行优势有限

2. JWT (JSON Web Token) 认证:
   HS256 (HMAC with SHA-256) vs RS256 (RSA Signature with SHA-256):

   HS256 (本项目使用):
      - 对称密钥: 签名和验证使用同一个 secret key
      - 优点:     实现简单、密钥管理简单、适合单体应用
      - 缺点:     所有需要验证 token 的服务都必须持有 secret key
                 如果 secret 泄露，攻击者可以伪造任何 token
      - 适用场景: 单体应用、微服务间的内部 token

   RS256:
      - 非对称密钥: 私钥签名（服务端持有）、公钥验证（任何服务可用）
      - 优点:     验证方不需要持有私钥，更安全
                 支持多服务验证同一 token（如 API Gateway）
      - 缺点:     需要管理公私钥对、实现复杂度更高
      - 适用场景: 微服务架构、第三方 API 认证、OAuth2/OIDC

   本项目选择 HS256 的原因:
      - 单体应用，只有一个后端服务
      - 没有 token 需要在多个服务间传递
      - 实现简单，配置简单（只需一个 JWT_SECRET 字符串）
      - 如果将来拆分为微服务，可以在 API Gateway 层验证并转换为内部 token

passlib 库说明:
    - passlib 是 Python 密码哈希库，支持 30+ 哈希算法
    - CryptContext 管理哈希方案的配置和自动升级
    - schemes=["bcrypt"]: 使用 bcrypt 算法
    - deprecated="auto": 自动处理过时的哈希方案迁移
    - 如果将来需要升级 bcrypt 的 cost factor，可以配置新的 scheme 并让旧哈希自动重新哈希

python-jose 库说明:
    - jose = JSON Object Signing and Encryption
    - 完整的 JWT 实现（JWS 签名 + JWE 加密 + JWK 密钥管理）
    - jwt.encode(): 创建签名 token
    - jwt.decode(): 验证签名 + 解析 payload
    - 注意: 和 PyJWT 功能类似，但 python-jose 对 JWE 支持更好
"""

from datetime import datetime, timedelta, timezone

# python-jose: JWT 的 Python 实现
# JWTError: 解码失败的基类（签名错误、过期、格式错误）
from jose import JWTError, jwt

# passlib: 密码哈希库
# CryptContext: 管理密码哈希方案的上下文对象
from passlib.context import CryptContext

from app.config import settings


# ============================================================================
# CryptContext — 密码哈希上下文
# ============================================================================
# schemes=["bcrypt"]: 使用 bcrypt 作为唯一的哈希方案
# deprecated="auto":  如果将来有旧的哈希方案，自动标记为"需要升级"
#
# bcrypt 的工作方式（通过 passlib）:
# 1. hash("mypassword") → "$2b$12$LJ3m4ys3Lk0TSwHlvDgFLO..."
#    - $2b$ : bcrypt 版本标识
#    - 12$  : cost factor (2^12 = 4096 轮迭代)
#    - 后面 : salt(22字符) + 哈希结果(31字符)
#
# 2. verify("mypassword", hash) → True/False
#    - 从哈希中提取 salt
#    - 用相同的 salt 和 cost factor 重新哈希明文
#    - 恒定时间比较（防止时序攻击: 即使用 == 比较会因字符差异而耗时不同，
#      攻击者可以通过测量响应时间逐个猜测字符）
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ============================================================================
# hash_password — bcrypt 哈希密码
# ============================================================================
def hash_password(password: str) -> str:
    """
    使用 bcrypt 对明文密码进行哈希。

    输入: "user_password_123"
    输出: "$2b$12$LJ3m4ys3Lk0TSwHlvDgFLO.aBcDeFgHiJkLmNoPqRsTuVwXyZ"

    这个函数是同步的（CPU 密集型），在异步路由中直接调用会阻塞事件循环。
    对于注册/登录这种低频操作，阻塞时间可以接受（bcrypt hash 约 200-500ms）。
    高并发场景应考虑 run_in_executor 放到线程池执行。
    """
    return pwd_context.hash(password)


# ============================================================================
# verify_password — 验证密码
# ============================================================================
def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    验证明文密码是否与 bcrypt 哈希匹配。

    工作流程:
        1. 从 hashed_password 中解析出 salt 和 cost factor
        2. 用相同的参数对 plain_password 进行哈希
        3. 恒定时间比较两个哈希值
        4. 返回 True（匹配）或 False（不匹配）

    同样也是同步的 CPU 密集型操作。
    """
    return pwd_context.verify(plain_password, hashed_password)


# ============================================================================
# create_access_token — 创建 JWT 访问令牌
# ============================================================================
def create_access_token(data: dict) -> str:
    """
    创建一个签名的 JWT access token。

    参数:
        data: 要编码到 token 中的数据，如 {"sub": "user-uuid-123"}

    JWT 结构:
        Header:   {"alg": "HS256", "typ": "JWT"}
        Payload:  {"sub": "user-uuid-123", "exp": 1717718400, "iat": 1717689600}
        Signature: HMAC-SHA256(base64(Header) + "." + base64(Payload), secret)

    最终 token 格式: header.payload.signature (三个 Base64URL 编码的字符串用点连接)

    exp (过期时间):
        - JWT 标准注册声明 (RFC 7519 Section 4.1.4)
        - 格式: Unix 时间戳（秒，UTC）
        - 由 jwt.encode 自动添加（传入的 dict 中已包含 "exp"）
        - 过期后 jwt.decode 会抛出 ExpiredSignatureError，被 JWTError 捕获

    iat (签发时间):
        - JWT 标准注册声明 (RFC 7519 Section 4.1.6)
        - jwt.encode 可能自动添加（取决于库实现）

    过期时间配置:
        settings.jwt_expire_minutes: 从 .env 读取，默认值通常在 settings.py 中定义
        建议: 开发环境 60 分钟，生产环境 15-30 分钟
        短期 token + refresh token 是更安全的设计（本项目简化版只有 access token）
    """
    # 复制 data 避免修改调用者的字典（防御性编程）
    to_encode = data.copy()

    # 计算过期时间
    # datetime.now(timezone.utc): 当前 UTC 时间（带时区信息）
    # timedelta(minutes=...):    N 分钟后的时间
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)

    # 将过期时间写入 payload
    to_encode.update({"exp": expire})

    # 编码并签名
    # algorithm=settings.jwt_algorithm: 从配置读取，默认 "HS256"
    return jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.jwt_algorithm)


# ============================================================================
# decode_access_token — 解码并验证 JWT
# ============================================================================
def decode_access_token(token: str) -> dict | None:
    """
    解码并验证 JWT access token。返回 payload 字典或 None。

    验证流程:
        1. 签名验证: 用 settings.jwt_secret 重新计算 HMAC-SHA256 签名
           → 如果 token 被篡改或 secret 不匹配 → JWTError
        2. 过期验证: 检查 exp 是否 < 当前 UTC 时间
           → 如果已过期 → ExpiredSignatureError (JWTError 的子类)
        3. 算法验证: 确保 token 使用了允许的算法（algorithms 白名单）
           → 如果使用其他算法（如 "none"）→ JWTError
        4. 格式验证: token 必须是三段 base64 字符串用点连接
           → 如果格式不对 → JWTError

    安全要点:
        - algorithms 白名单: 必须指定允许的算法，否则攻击者可能用 "none" 算法（无签名）伪造 token
        - 返回值设计: None 而非抛异常 → 调用方可以自行决定如何处理（401 还是忽略）
        - 不在此处做用户存在性检查: 解码只是验证 token 本身是否有效，
          用户是否存在由调用方（get_current_user）检查
    """
    try:
        # jwt.decode 自动验证签名、过期时间、算法
        # algorithms 参数是白名单 — token 中的 alg 必须在此列表中
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm]  # 例如 ["HS256"]
        )
        return payload
    except JWTError:
        # JWTError 是所有 JWT 相关异常的基类:
        #   - JWTClaimsError:   claims 验证失败
        #   - ExpiredSignatureError: token 已过期
        #   - JWTError:         签名无效、格式错误等
        # 统一返回 None，由调用方决定如何处理
        return None
