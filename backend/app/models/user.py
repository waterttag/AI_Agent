"""
User ORM model.

用户 ORM 模型。
使用 SQLAlchemy 2.0 声明式映射（Mapped + mapped_column），
与 PostgreSQL 的 UUID 原生支持无缝集成。
"""
# =============================================================================
# 用户模型 (User Model)
# =============================================================================
# 本模块定义了用户表（users）的 ORM 映射。
#
# 设计决策：
# 1. 主键使用 UUID 字符串（String(36)）而非自增整数：
#    - 分布式友好：多服务实例可并行生成 ID，无需中心化 ID 分配器
#    - 安全：UUID 不可预测，避免通过递增 ID 枚举用户（URL 防护）
#    - 前端友好：前端可离线生成 ID 用于乐观更新
# 2. 使用 String(36) 而非 PostgreSQL 原生 UUID 类型：
#    - 跨数据库兼容：SQLite/MySQL 没有原生 UUID 类型，String(36) 通用
#    - 调试友好：字符串形式的 UUID 比二进制更易读
#    - ORM 兼容：部分 ORM 对 PostgreSQL UUID 类型的序列化/反序列化支持有坑
# 3. 密码使用 bcrypt 哈希存储（业务层处理，模型只存哈希结果）：
#    - bcrypt 自带盐值（salt），抗彩虹表攻击
#    - bcrypt 计算慢（可配置 work factor），暴力破解成本极高
#    - 模型层只存 password_hash，明文密码绝不落库
# 4. role 字段用于权限控制（RBAC - 基于角色的访问控制）：
#    - "player"：普通用户，默认角色
#    - 扩展预留："admin"、"moderator" 等
#    - 使用字符串而非外键关联角色表：简单场景下避免多表 JOIN 开销
# 5. created_at / updated_at 使用数据库服务器时间（server_default=func.now()）：
#    - 保证时间戳一致性（不依赖应用服务器时钟）
#    - updated_at 的 onupdate 确保每次 UPDATE 自动更新

import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, func
from sqlalchemy.dialects.postgresql import UUID  # 导入 PostgreSQL 原生 UUID 类型（备用，实际未使用）
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base  # 导入声明式基类，所有模型继承自此


class User(Base):
    """
    用户数据库模型。

    映射到数据库中的 users 表，存储用户注册信息、
    登录凭证（密码哈希）和角色权限。
    """
    # ---- 表名配置 ----
    # 显式指定表名，遵循 SQLAlchemy 命名规范（复数形式）
    __tablename__ = "users"

    # ---- 主键 ----
    # UUID 字符串主键：
    # - String(36)：存储去掉连字符的 UUID 共 32 字符 + 4 连字符 = 36 字符
    # - default=lambda: str(uuid.uuid4())：Python 端生成 UUID v4（随机）
    #   lambda 确保每次插入调用时生成新值，而不是模块加载时固化
    # - 不使用 server_default：数据库端生成 UUID 需要扩展（pgcrypto），
    #   且不同数据库函数不同，应用端生成更可移植
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    # ---- 用户名 ----
    # 唯一索引保证用户名全局唯一，用于展示和 @ 提及
    # nullable=False 与 unique=True 共同保证数据完整性
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    # ---- 邮箱 ----
    # 也设置 unique=True 和 index=True：
    # - 登录时通过邮箱查找用户，索引加速查询
    # - 唯一约束防止同一邮箱重复注册
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    # ---- 密码哈希 ----
    # 存储 bcrypt 哈希结果（业务层在写入前处理），典型长度 60 字符
    # 使用 255 长度留足余量，兼容未来更强的哈希算法
    # 注意：绝不在此存储明文密码
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    # ---- 角色 ----
    # role 字段实现简单的 RBAC 权限模型：
    # - "player"：默认角色，可创建/分享游戏
    # - 可扩展为 "admin"、"moderator" 等
    # - 使用字符串比枚举更灵活（新增角色无需 ALTER TYPE）
    # - 但缺少数据库层面的约束验证（可配合 Pydantic validator 在应用层校验）
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="player")
    # ---- 创建时间 ----
    # server_default=func.now()：使用数据库服务器时间（如 PostgreSQL 的 NOW()），
    # 而非 Python 的 datetime.now()，确保多服务器时区一致
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    # ---- 更新时间 ----
    # onupdate=func.now()：每次行 UPDATE 时自动刷新时间戳
    # 注意：onupdate 是 SQLAlchemy 应用层行为，数据库不强制执行
    # 如果运行原始 SQL UPDATE，此字段不会自动更新
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        """
        开发者友好的字符串表示。
        避免在 __repr__ 中暴露敏感信息（如 email、password_hash）。
        """
        return f"<User(id={self.id}, username={self.username})>"
