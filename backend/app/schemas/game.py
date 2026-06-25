"""
Game-related Pydantic schemas.

游戏相关的 Pydantic 数据验证模型（Schema）。

本模块覆盖了游戏的完整 CRUD 数据流：
- 创建（GameCreate）：用户输入的游戏元数据
- 更新（GameUpdate）：部分更新的字段（全部 Optional）
- 响应（GameResponse）：返回给前端的完整游戏信息
- 列表（GameListResponse）：分页列表的标准化格式
- AI 生成（GenerateRequest）：提交 AI 生成任务的请求体
"""
# =============================================================================
# 游戏 Schema 模块
# =============================================================================

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


# =============================================================================
# GameCreate - 创建游戏请求体
# =============================================================================
class GameCreate(BaseModel):
    """
    创建（或 AI 预创建）游戏时的请求体 Schema。

    所有必需字段都有明确约束，Field 提供：
    1. 类型验证（str、list 等）
    2. 长度限制（防止数据库溢出和恶意超长输入）
    3. 默认值（减少前端必填字段数量）
    """
    # ---- 游戏标题 ----
    # min_length=1：确保标题不为空字符串（与数据库 nullable=False 呼应）
    # max_length=200：与数据库 String(200) 对齐
    title: str = Field(..., min_length=1, max_length=200)
    # ---- 游戏描述 ----
    # default=""：允许创建时不填描述（草稿状态）
    # max_length=5000：限制描述长度，防止数据库存储过大文本
    #   注意：此处与数据库 Text 类型不完全一致（Text 无长度限制），
    #   在应用层加限制是一个安全措施（defense in depth）
    description: str = Field(default="", max_length=5000)
    # ---- 标签列表 ----
    # default_factory=list：每个请求创建一个新的空列表
    #   为什么用 default_factory 而非 default=[]：
    #   Python 中 default=[] 会导致所有实例共享同一个列表对象（可变默认参数的经典陷阱）
    #   default_factory=list 每次实例化调用 list() 返回新列表，互不影响
    # 标签值如：["动作", "冒险", "2D", "像素风"]
    tags: list[str] = Field(default_factory=list)
    # ---- 生成提示词 ----
    # Optional[str]：允许为 None（手动创建的游戏无需提示词）
    # max_length=10000：足够容纳详细的游戏生成指令，同时防止滥用
    # 提示词示例："创建一个 2D 平台跳跃游戏，主角是猫，有 5 个关卡..."
    prompt_text: Optional[str] = Field(default=None, max_length=10000)


# =============================================================================
# GameUpdate - 更新游戏请求体
# =============================================================================
class GameUpdate(BaseModel):
    """
    更新游戏时的请求体 Schema。

    所有字段都是 Optional：
    - PATCH 语义：仅更新客户端提供的字段，未提供的字段保持不变
    - 前端可以只发送变更的字段，减少不必要的网络传输
    - 避免 PUT 语义下的"全量替换"问题（需要客户端先获取完整数据再提交）

    更新约束：
    - title/description 的 min_length 仅在提供值时生效
    - status 无枚举校验（留给业务层处理状态机迁移合法性）
    """
    # ---- 标题 ----
    # Optional + min_length=1：提供了就不能是空字符串
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    # ---- 描述 ----
    description: Optional[str] = Field(default=None, max_length=5000)
    # ---- 标签 ----
    # Optional[list[str]]：None 表示不更新标签，
    # 如果提供了则替换整个标签列表（不是追加）
    tags: Optional[list[str]] = None
    # ---- 封面图 URL ----
    # 允许前端直接设置（通常由上传接口返回 URL 后再赋值）
    cover_image_url: Optional[str] = None
    # ---- 状态 ----
    # 允许前端修改游戏状态（如发布 draft→published）
    # 业务层应校验状态迁移是否合法（如不能从 archived 回到 draft）
    # 这里不做 Pydantic 层的枚举校验，因为状态集合可能变化
    status: Optional[str] = None


# =============================================================================
# GameAssetResponse - 游戏资源响应体
# =============================================================================
class GameAssetResponse(BaseModel):
    """
    游戏资源文件的 API 响应 Schema。

    嵌套在 GameResponse.assets 中，返回给前端用于渲染游戏资源。
    不返回 oss_key（内部运维信息），只返回前端需要的 oss_url。
    """
    id: str               # 资源 UUID
    game_id: str          # 所属游戏 ID（前端可能用于过滤）
    asset_type: str       # 资源类型："image" / "audio"
    original_filename: str # 原始文件名（用于下载时还原）
    oss_url: str          # 可直接访问的 OSS URL（前端直接使用）
    file_size: Optional[int] = None  # 文件大小（字节），可为空
    created_at: datetime  # 上传时间

    model_config = {"from_attributes": True}


# =============================================================================
# GameResponse - 游戏详情响应体
# =============================================================================
class GameResponse(BaseModel):
    """
    游戏详情/列表项的 API 响应 Schema。

    这是最核心的响应模型，被 GameListResponse 嵌套使用。

    重要字段说明：
    - author_name：不在数据库 games 表中，而是通过 JOIN 从 users 表获取
      响应构建时业务层填充此字段（如 game.author.username）
    - status：控制前端展示"草稿"/"已发布"/"已归档"的标签
    - assets：嵌套的 GameAssetResponse 列表，通过 ORM relationship 获取
    """
    id: str                    # 游戏 UUID
    title: str                 # 游戏标题
    description: str           # 游戏描述
    cover_image_url: Optional[str] = None  # 封面图 URL（草稿可能无封面）
    game_url: Optional[str] = None         # 游戏可玩 URL（发布后才有）
    author_id: str             # 作者用户 ID
    # ---- 作者名称 ----
    # 这是一个"虚拟"字段：数据库没有此列，由业务层填充
    # 为什么不在数据库层做 JOIN 返回：
    #   - 解耦：Schema 独立于 ORM 查询方式
    #   - 灵活性：可以从缓存（Redis）获取而非总是 JOIN
    #   - 性能：避免某些查询路径下的 N+1 问题
    author_name: Optional[str] = None
    # ---- 标签 ----
    # 使用 list 而非 list[str]：兼容 ORM 返回的各种可迭代类型
    # default_factory=list：当 ORM 对象 tags 为 None 时使用空列表
    tags: list = Field(default_factory=list)
    # ---- 状态 ----
    # draft / published / archived
    # 前端根据此字段显示不同的 UI 操作按钮
    status: str
    # ---- 生成提示词 ----
    # 仅在详情页展示（让用户知道自己输入了什么）
    prompt_text: Optional[str] = None
    # ---- 播放次数（热度指标） ----
    # 用于排序（最多播放）和展示（"已播放 1.2k 次"）
    # default=0 而非 0（int 可以有默认值，Field 的 default 参数明确写数值）
    play_count: int = 0
    # ---- 时间戳 ----
    created_at: datetime   # 游戏创建时间
    updated_at: datetime   # 最后更新时间
    # ---- 资源列表 ----
    # 嵌套的资产响应列表，通过 Game.assets ORM relationship 获取
    assets: list[GameAssetResponse] = Field(default_factory=list)

    model_config = {"from_attributes": True}


# =============================================================================
# GameListResponse - 分页列表响应体
# =============================================================================
class GameListResponse(BaseModel):
    """
    分页游戏列表的标准化响应格式。

    标准分页四元组，符合 RESTful API 最佳实践：
    - items：当前页的数据列表
    - total：总记录数（用于前端计算总页数：ceil(total / size)）
    - page：当前页码（从 1 开始）
    - size：每页记录数
    """
    items: list[GameResponse]  # 当前页的游戏列表
    total: int                  # 符合条件的总游戏数（用于分页导航）
    page: int                   # 当前页码
    size: int                   # 每页数量


# =============================================================================
# GenerateRequest - AI 生成请求体
# =============================================================================
class GenerateRequest(BaseModel):
    """
    提交 AI 游戏生成任务的请求体 Schema。

    用户输入一段自然语言描述，AI 将其转化为可玩的 HTML 游戏。
    """
    # ---- 生成提示词 ----
    # min_length=10：太短的提示词没有足够信息让 AI 生成有意义的游戏
    # max_length=10000：足够详细描述复杂游戏玩法
    prompt_text: str = Field(..., min_length=10, max_length=10000)
    # ---- 模型偏好 ----
    # 可选字段，允许用户指定使用的 AI 模型
    # 例如："claude-sonnet"、"gpt-4o"
    # None 表示使用默认模型（后端配置）
    # 实际使用需要业务层校验模型是否可用
    model_preference: Optional[str] = None
