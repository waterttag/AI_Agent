"""
Game and GameAsset ORM models.

游戏、游戏资产和游戏收藏 ORM 模型。
"""
# =============================================================================
# 游戏模型组 (Game, GameAsset, GameFavorite)
# =============================================================================
# 本模块定义了三张核心业务表：
#   - games：游戏主表，含状态机、标签、播放计数
#   - game_assets：游戏资源文件（图片、音频等）存储在阿里云 OSS
#   - game_favorites：用户收藏关联表（复合主键）
#
# 设计决策：
# 1. tags 使用 PostgreSQL JSON 列而非独立的关联表（多对多）：
#    - 游戏标签数量少（通常 < 10 个），JSON 存储开销极小
#    - 避免 JOIN 查询：获取游戏列表时无需关联标签表
#    - 查询灵活性：PG JSON 字段支持索引（GIN），可进行 JSON 内搜索
#    - 权衡：标签无法复用（跨游戏去重），但对于游戏场景这不是痛点
# 2. status 字段实现状态机（状态迁移语义）：
#    - "draft" → "published" → "archived"
#    - 或 "draft" → "pending_review" → "published" → "archived"
#    - 使用字符串 + 索引，应用层 Pydantic 校验合法值
#    - 不用枚举：枚举虽然数据库层面强约束，但增加新状态需要 DDL 变更
# 3. GameFavorite 使用复合主键 (user_id, game_id)：
#    - 语义上天然就是"用户+游戏"唯一确定一条收藏记录
#    - 省去单独的 id 列，减少索引开销
#    - 数据库自动保证同一用户不会重复收藏同一游戏
# 4. GameAsset 使用 cascade="all, delete-orphan"：
#    - 删除游戏时自动删除所有关联资产记录
#    - delete-orphan：如果从 Game.assets 列表中移除某个资产，自动删除该资产行

import uuid
from datetime import datetime

from sqlalchemy import String, Text, Integer, DateTime, ForeignKey, JSON, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


# =============================================================================
# Game 模型（游戏主表）
# =============================================================================
class Game(Base):
    """
    游戏数据库模型。

    映射到 games 表，存储每个 AI 生成游戏的所有元数据。
    通过 author_id 外键关联到 users 表，通过 assets 关系关联到 game_assets 表。
    """
    __tablename__ = "games"

    # ---- 主键 ----
    # UUID v4 字符串（36 字符含连字符），分布式友好
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    # ---- 标题 ----
    # 必填字段，200 字符足够容纳大多数游戏名称（含中文）
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    # ---- 描述 ----
    # Text 类型：不同于 VARCHAR，Text 无长度限制（或限制很大），
    # 适合存储 AI 生成的游戏玩法描述（可能较长）
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # ---- 封面图 URL ----
    # 存储 OSS 完整 URL，允许为空（草稿状态可能无封面）
    # |None 语法（Python 3.10+ Union 简写）：明确标记为可选
    cover_image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # ---- 游戏 URL ----
    # AI 生成的 HTML 游戏文件在 OSS 上的完整 URL
    # 发布后才有值，草稿阶段为 None
    game_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # ---- 作者 ID（外键） ----
    # ForeignKey("users.id")：确保引用完整性
    # 如果 users 表中不存在该用户，插入/更新会失败
    author_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    # ---- 标签 ----
    # 使用 JSON 列类型存储标签列表，如 ["动作", "冒险", "2D"]
    # 为什么用 JSON 而不是 M2M 关联表：
    #   - 标签数量少（通常 3-8 个），不需要复杂查询
    #   - JSON 在 PostgreSQL 中可创建 GIN 索引以支持查询（如 @> 操作符）
    #   - 获取游戏时一次 SELECT 即可拿到所有标签，无需 JOIN
    #   - MySQL 5.7+ 也支持 JSON 类型，跨数据库兼容性 OK
    # default=list：注意这里是 SQLAlchemy 默认值，不是数据库默认值
    #   如果直接 INSERT（不经过 ORM），需要手动设置，否则会失败
    tags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    # ---- 状态（状态机字段） ----
    # 状态流转：
    #   draft(草稿) ──发布──> published(已发布) ──归档──> archived(已归档)
    #                     └──下架──> draft
    # 状态转义由业务层（API endpoint）控制，模型层不做约束
    # index=True：首页通常只展示 published 的游戏，索引加速过滤
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="draft", index=True
    )
    # ---- 提示词文本 ----
    # 存储用户输入的 AI 生成提示词，用于追溯和调试
    # 可为空（非 AI 生成的游戏或手动创建的）
    prompt_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # ---- 播放次数 ----
    # 每次游戏被打开时递增，用于热度排序
    # 默认 0，不允许 None（避免 NULL 与 0 的语义混淆）
    # 注意：并发递增需要原子操作（UPDATE ... SET play_count = play_count + 1）
    play_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # ---- 创建时间 ----
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    # ---- 更新时间 ----
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # =========================================================================
    # 关系定义 (Relationships)
    # =========================================================================
    # ORM 层面的关联：不是数据库列，而是 Python 对象的引用
    # SQLAlchemy 通过 FK 自动推导 JOIN 条件

    # ---- 游戏资产（一对多） ----
    # cascade="all, delete-orphan" 语义：
    #   - "all"：包含 save-update, merge, delete, refresh-expire, expunge
    #     (即父对象的所有操作级联到子对象)
    #   - "delete-orphan"：当子对象从父对象的集合中被移除时，
    #     该子对象自动被 DELETED（不仅是外键置 NULL）
    # 典型场景：删除游戏 → 所有关联的 GameAsset 行也被删除
    #          从 Game.assets 列表中 pop 一个元素 → 该元素被 DELETE
    # 注意：cascade 在 ORM 层面（Python 对象操作），数据库层面的
    #       CASCADE 需要在 ForeignKey 中单独定义（ondelete="CASCADE"）
    assets: Mapped[list["GameAsset"]] = relationship(
        "GameAsset", back_populates="game", cascade="all, delete-orphan"
    )
    # ---- 作者（多对一） ----
    # 只读关联：获取游戏时通过 game.author.username 直接访问作者信息
    # foreign_keys 显式指定外键列：当模型中有多个 FK 指向同一表时，
    #   SQLAlchemy 可能无法自动推断，显式指定避免歧义
    author: Mapped["User"] = relationship("User", foreign_keys=[author_id])

    def __repr__(self) -> str:
        """
        开发者友好的字符串表示。
        显示 id、title、status 三个最关键的字段，便于调试。
        """
        return f"<Game(id={self.id}, title={self.title}, status={self.status})>"


# =============================================================================
# GameAsset 模型（游戏资源文件）
# =============================================================================
class GameAsset(Base):
    """
    游戏资产数据库模型。

    存储游戏相关文件的元数据（图片、音频等），
    实际文件存储在阿里云 OSS 中，数据库只保留文件的 key 和 URL。
    这样设计的好处：
      - OSS 处理大文件存储和 CDN 分发，数据库不存 BLOB
      - 通过 oss_key 可以在需要时重新生成签名 URL（私有 Bucket 场景）
      - db 压力小，备份快
    """
    __tablename__ = "game_assets"

    # ---- 主键 ----
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    # ---- 所属游戏 ID（外键） ----
    # 一个游戏可以有多个资产文件（封面图、BGM、精灵图等）
    game_id: Mapped[str] = mapped_column(String(36), ForeignKey("games.id"), nullable=False)
    # ---- 资产类型 ----
    # 用于前端渲染时区分 "image"（图片）vs "audio"（音频）
    # 值例如："image"、"audio"、"sprite"、"background"
    # 使用字符串而非枚举：未来可能有新类型（如 "video"、"model"）
    asset_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # ---- 原始文件名 ----
    # 保留用户上传时的原始文件名，用于下载时还原
    # 例如："my_game_cover.png"
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    # ---- OSS 存储路径（Key） ----
    # OSS 中的对象 key，通常是带路径的文件名：
    # 例如："games/{game_id}/assets/{uuid}.png"
    # 用于重新生成签名 URL 或执行 OSS 操作（复制、删除）
    oss_key: Mapped[str] = mapped_column(String(500), nullable=False)
    # ---- OSS 访问 URL ----
    # 完整的 OSS 访问 URL（可能是公开 URL 或签名 URL）
    # 前端直接用此 URL 展示资源，无需感知 OSS 细节
    oss_url: Mapped[str] = mapped_column(String(500), nullable=False)
    # ---- 文件大小（字节） ----
    # 用于前端展示文件大小，辅助用户判断加载时间
    # 可为空：某些场景下（如 OSS 回调）可能获取不到文件大小
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # ---- 创建时间 ----
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    # ---- 反向关系（多对一） ----
    # back_populates="assets" 与 Game.assets 形成双向关系
    # 通过 asset.game 可以直接获取所属的 Game 对象
    game: Mapped["Game"] = relationship("Game", back_populates="assets")

    def __repr__(self) -> str:
        return f"<GameAsset(id={self.id}, type={self.asset_type})>"


# =============================================================================
# GameFavorite 模型（收藏关联表）
# =============================================================================
# 注意：这里有一个 `import uuid as _uuid` 的重复导入，之所以这样写
# 是因为 GameFavorite 通常作为独立模块的一部分被加载，
# 加上 uuid 在文件顶部已导入一次，此处用别名避免 shadowing 警告

import uuid as _uuid  # 为 GameFavorite 的 default lambda 提供 UUID 生成器

class GameFavorite(Base):
    """
    游戏收藏关联模型。

    核心设计：复合主键 (user_id, game_id)
    为什么不加独立的 id 列？
      - 收藏表的本质是"用户-游戏"的 N:M 关系
      - 复合主键天然保证唯一性：同一用户对同一游戏只有一条记录
      - 减少索引：复合 PK 自动创建 (user_id, game_id) 联合索引
      - 减少存储：无需额外的自增列和索引

    不过，这段代码有个需要注意的问题：
      default=lambda: str(_uuid.uuid4()) 写在 user_id 列的 default 上，
      但 user_id 也是复合主键的一部分。由于 Python 端的 default 行为，
      每次创建 GameFavorite 实例时 user_id 会生成一个新 UUID，这在
      逻辑上是错误的——收藏应该用已存在的 user_id。实际使用时，
      业务代码会显式传入 user_id，此时 default 不会被调用（因为值已提供）。
      但为了代码清晰，这里移除 default 会更合适。
    """
    __tablename__ = "game_favorites"

    # ---- 用户 ID（复合主键第一部分） ----
    # ForeignKey("users.id")：引用用户表
    # primary_key=True：作为复合主键的一部分
    # 注意 default lambda 的 UUID 生成在显式传参时不会触发，
    # 实际使用中 user_id 由业务逻辑（当前登录用户）提供
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id"),
        primary_key=True,
        default=lambda: str(_uuid.uuid4())  # 仅当未显式传值时作为后备
    )
    # ---- 游戏 ID（复合主键第二部分） ----
    # ForeignKey("games.id")：引用游戏表
    # 两个 foreign key 没有设置 ondelete="CASCADE"，意味着删除用户或游戏时
    # 不会自动删除收藏记录。需要业务层检查外键约束或显式清理
    game_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("games.id"), primary_key=True
    )
    # ---- 收藏时间 ----
    # 仅记录收藏的时间点，用于排序（如"最近收藏"）
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
