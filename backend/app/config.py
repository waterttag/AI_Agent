"""Application configuration via Pydantic Settings.

使用 Pydantic Settings 管理所有环境变量和应用配置。
Pydantic Settings 会自动从 .env 文件和环境变量中加载配置，
提供类型验证、默认值和类型转换能力，比直接使用 os.environ 更安全、更可维护。
"""

import os
from pathlib import Path
from pydantic_settings import BaseSettings

# [项目根目录解析]
# 从当前文件的绝对路径向上三级推导项目根目录。
# 当前文件: backend/app/config.py
#   -> parent       = backend/app/
#   -> parent.parent      = backend/
#   -> parent.parent.parent = 项目根目录 (D:\AI_Agent)
# 这样做的好处是：无论从哪个目录启动应用，都能正确定位项目根目录，
# 从而可靠地找到 .env 文件和 SQLite 数据库文件。
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# .env 文件的绝对路径，Pydantic Settings 会根据此路径加载环境变量。
ENV_FILE = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    """所有环境变量配置，优先从 .env 文件加载，其次使用系统环境变量。

    Pydantic BaseSettings 的加载优先级（由高到低）：
    1. 系统环境变量（export 或 set 设置的）
    2. .env 文件中的变量
    3. 类属性中定义的默认值

    这意味着你可以通过设置环境变量来覆盖 .env 文件中的任何配置，
    非常适合 Docker 部署时通过 -e 参数注入配置。
    """

    # ==================== 数据库配置 ====================
    # database_url 为空字符串时，get_database_url() 会回退到默认 SQLite 路径。
    # 支持格式示例：
    #   - PostgreSQL: postgresql+asyncpg://user:pass@host:5432/dbname
    #   - SQLite:     留空，自动回退到项目根目录/app.db
    # 注意使用 asyncpg 或 aiosqlite 等异步驱动，因为整个应用基于异步 SQLAlchemy。
    database_url: str = ""  # 如果为空，回退到默认 SQLite

    def get_database_url(self) -> str:
        """返回有效的数据库连接 URL，带智能回退逻辑。

        设计思路：
        1. 如果显式设置了 database_url（如 PostgreSQL），直接使用。
        2. 否则回退到 SQLite：
           - 优先检查 /data 目录是否存在（Docker 持久卷挂载点），
             如果存在，将数据库文件放到 /data/app.db，这样容器重启后数据不丢失。
           - 如果不在 Docker 环境中（无 /data 目录），使用项目根目录下的 app.db。

        这种"默认值 + 自动检测"模式让开发者在本地不需要任何配置就能跑起来，
        同时在生产环境只需设置一两个环境变量即可切换数据库。
        """
        if self.database_url:
            return self.database_url
        # 默认使用 SQLite，优先放在 Docker 持久卷路径
        db_path = PROJECT_ROOT / "app.db"
        if os.path.exists("/data"):
            # /data 是 Docker 容器中常见的持久化数据目录，
            # 将 SQLite 文件放在此处可以避免容器重启时数据丢失。
            db_path = Path("/data/app.db")
        # aiosqlite 是 SQLite 的异步驱动，通过 asyncio 事件循环实现非阻塞 SQL 操作。
        # 虽然 SQLite 本身不支持网络连接，但 aiosqlite 在同一线程内提供了异步接口，
        # 与 SQLAlchemy 的异步引擎无缝集成。
        return f"sqlite+aiosqlite:///{db_path}"

    # ==================== Redis 配置 ====================
    # Redis 主要用于缓存（如热门游戏列表）和会话管理。
    # 格式: redis://[[username]:[password]]@host:port/db
    # db=0 表示使用 Redis 的 0 号数据库（Redis 默认有 16 个逻辑数据库，编号 0-15）。
    redis_url: str = "redis://localhost:6379/0"

    # ==================== MinIO 对象存储配置 ====================
    # MinIO 是一个兼容 Amazon S3 API 的开源对象存储服务。
    # 本项目用它存储生成的 HTML 游戏文件，替代直接存储在本地文件系统或数据库中。
    # 这样设计的好处：
    #   - 游戏文件与后端服务解耦，可独立扩展
    #   - 支持 CDN 分发，提升加载速度
    #   - 兼容 S3 API，可无缝切换到 AWS S3 或阿里云 OSS
    minio_endpoint: str = "localhost:9000"       # MinIO 服务地址
    minio_access_key: str = "minioadmin"         # 访问密钥（默认管理员账号）
    minio_secret_key: str = "minioadmin"         # 密钥（默认管理员密码）
    minio_bucket: str = "ai-game-platform"      # 存储桶名称（类似文件系统中的"文件夹"）
    minio_secure: bool = False                  # 是否使用 HTTPS（本地开发默认不启用）

    # ==================== JWT 认证配置 ====================
    # JWT (JSON Web Token) 是一种无状态的认证机制。
    # 用户登录后，服务器签发一个包含用户信息的签名令牌，
    # 后续请求携带此令牌即可证明身份，无需每次查数据库或 Redis。
    # 令牌包含三部分：Header.Payload.Signature，通过 Base64 编码后以点号分隔。
    jwt_secret: str = "change-me-in-production"  # 签名密钥，生产环境务必修改！
    jwt_algorithm: str = "HS256"                 # 签名算法（HMAC-SHA256，对称加密）
    jwt_expire_minutes: int = 1440               # 令牌有效期（分钟），1440 = 24 小时

    # ==================== LLM 大语言模型配置 ====================
    # 项目支持多种 LLM 提供商，通过 llm_provider 切换。
    # "none" 表示不启用 AI 生成功能（离线模式），游戏平台仍可正常使用预置游戏。
    # 为什么设计泛化的 OpenAI 兼容接口：
    #   大多数 LLM 服务商（DeepSeek、通义千问、智谱等）都提供 OpenAI 兼容 API，
    #   通过统一的 base_url + api_key + model 模式，可以在不改代码的情况下切换模型。
    llm_provider: str = "none"                    # 当前使用的 LLM 提供商
    llm_api_key: str = ""                         # API 密钥
    llm_model: str = "deepseek-chat"              # 模型名称
    llm_api_base_url: str = ""                    # 自定义 API 端点（兼容 OpenAI 协议的第三方服务）

    # ==================== CORS 跨域配置 ====================
    # CORS (Cross-Origin Resource Sharing) 跨域资源共享。
    # 前端开发时通常运行在 localhost:5173 (Vite) 或 localhost:3000 (其他)，
    # 与后端 localhost:8000 不同源（端口不同），浏览器会阻止跨域请求。
    # 这里配置允许的源列表，实际 main.py 中使用 allow_origins=["*"] 放宽了限制。
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # Pydantic Settings 的模型配置。
    # env_file:     指定 .env 文件路径，启动时自动加载
    # env_file_encoding: .env 文件的字符编码
    # extra: "ignore" 表示忽略 .env 中未在 Settings 类定义的额外键，
    #   这样可以安全地在 .env 中存放其他服务的配置而不影响应用启动。
    model_config = {"env_file": str(ENV_FILE), "env_file_encoding": "utf-8", "extra": "ignore"}


# 模块级单例，整个应用共享这一个配置实例。
# 在模块首次 import 时完成初始化（加载 .env 文件 + 环境变量），
# 之后所有模块通过 from app.config import settings 获取同一个实例。
settings = Settings()
