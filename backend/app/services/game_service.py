"""
游戏 CRUD 业务逻辑层 (Game CRUD Business Logic)
================================================
WHAT: 封装游戏和资源的创建、查询（含分页和标签过滤）、更新、删除等核心业务逻辑。
WHY:  将数据访问代码与 HTTP 路由分离，Router 层只关心"接收什么参数、返回什么状态码"，
      Service 层关心"如何操作数据库"。

核心技术要点:
1. selectinload: 预加载关联对象，解决 N+1 查询和异步 greenlet 问题
2. cast(Text).like: SQLite 中 JSON 数组搜索的跨数据库兼容方案
3. model_dump(exclude_unset=True): 只更新客户端实际传了的字段
"""

from sqlalchemy import select, func, Text    # Text 用于跨 DB 的 JSON 字段类型转换
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload       # 预加载关联对象的核心工具

from app.models.game import Game, GameAsset
from app.models.user import User
from app.schemas.game import GameCreate, GameUpdate, GameListResponse, GameResponse


# ============================================================================
# create_game — 创建游戏草稿
# ============================================================================
async def create_game(db: AsyncSession, author_id: str, data: GameCreate) -> Game:
    """
    创建新的游戏记录，初始状态为 "draft"。

    状态生命周期:
        draft      → 用户刚创建，尚未发布
        generating → 正在 AI 生成中
        preview    → 生成完毕，待发布
        published  → 已发布，公开可见
        failed     → 生成失败
        archived   → 已归档（不可见）

    注意: 这里不加载关联关系，返回的是"裸"Game 对象。
         调用方（Route 层）需要重新用 get_game（带 selectinload）查询来获取完整数据。
    """
    game = Game(
        title=data.title,
        description=data.description,
        tags=data.tags,
        prompt_text=data.prompt_text,
        author_id=author_id,
        status="draft",
    )
    db.add(game)
    await db.commit()
    await db.refresh(game)  # 获取数据库生成的字段（如 created_at）
    return game


# ============================================================================
# get_game — 获取单个游戏（带关联数据）
# ============================================================================
async def get_game(db: AsyncSession, game_id: str) -> Game | None:
    """
    获取单个游戏，同时预加载 assets 和 author 关联。

    selectinload 详解:
        - SQLAlchemy 默认 relationship 使用 lazy="select"（懒加载）
        - 懒加载意味着首次访问 game.assets 时才发 SQL 查询
        - 在异步上下文（asyncio）中，懒加载会触发 greenlet 错误:
          "greenlet_spawn has not been called; can't call await_() here"
        - 这是因为 SQLAlchemy 的异步模式需要在正确的协程上下文中执行 I/O
        - selectinload 在初始查询中用 LEFT JOIN 一次性加载所有关联数据
        - 生成的 SQL 类似:
          SELECT ... FROM games LEFT JOIN game_assets ON ... WHERE games.id = ?
          然后 SELECT ... FROM users WHERE users.id IN (...)

    为什么用 selectinload 而不是 joinedload？
        - joinedload: 用单个大 JOIN 查询加载所有数据 → 数据重复（主表行 * 关联表行）
        - selectinload: 分两次查询 → 先查主表，再 IN 查询关联表 → 数据量小、更清晰
        - 对于一对多关系（Game -> Assets），selectinload 更高效
        - 对于多对一关系（Game -> Author），两者差异不大
    """
    result = await db.execute(
        select(Game)
        .where(Game.id == game_id)
        .options(
            selectinload(Game.assets),   # 预加载该游戏的所有资源文件
            selectinload(Game.author),   # 预加载作者 User 对象
        )
    )
    return result.scalar_one_or_none()


# ============================================================================
# list_games — 游戏列表（分页、筛选）
# ============================================================================
async def list_games(
    db: AsyncSession,
    status: str = "published",
    tag: str | None = None,
    page: int = 1,
    size: int = 12,
) -> GameListResponse:
    """
    查询游戏列表，支持状态筛选、标签过滤和分页。

    ---- 状态筛选逻辑 ----
    "listed" 特殊值: 同时显示 published 和 preview 两种状态。
    为什么需要 "listed"？
        - 前端需要"公开列表"视图，包含已发布 + 待审核的内容
        - 不直接用两个独立状态查询是因为要保持单一查询参数的简洁性
        - 前端只需要传 ?status=listed，后端统一处理

    ---- JSON 标签搜索的核心技术决策 ----

    问题: SQLite 的 tags 列是 JSON 类型（实际存为 TEXT），如何搜索 "[tag1, tag2]" 中的某个 tag？

    方案对比:
        1. JSON.contains (PostgreSQL JSONB 专用):
           - Game.tags.contains(["射击"]) 在 PostgreSQL 中生成 @> 操作符
           - SQLite 不支持 → 只能在 PG 环境使用，无法跨数据库

        2. cast(Text).like (本方案):
           - Game.tags.cast(Text).like('%\"射击\"%')
           - 将 JSON 列转为文本，用 LIKE 做子串匹配
           - 使用引号包裹搜索词 ("{tag}") 避免误匹配:
             如搜索 "RPG" 不会匹配到 "ARPG"（因为匹配的是 "RPG"）
           - 兼容 SQLite 和 PostgreSQL（PostgreSQL 上 JSONB 也可以 cast 为 Text）

        3. 单独建标签表（tag + game_tag 多对多关系）:
           - 正规化的关系模型，查询效率最高
           - 但增加了数据库复杂度（多两张表、JOIN 查询）
           - 当前项目中标签是轻量级的元数据，JSON 数组足够

    为什么选择 cast(Text).like？
        - 跨数据库兼容（SQLite 开发 + PostgreSQL 生产）
        - 实现简单，无需额外表结构
        - 标签搜索不是高频操作，性能差异可忽略
        - 引号包裹确保精确匹配语义

    ---- 分页 ----
    offset = (page - 1) * size
    例如: page=1, size=12 → offset=0, 取前 12 条
          page=2, size=12 → offset=12, 跳过前 12 条取 13-24 条
    """
    # 基础查询
    base_query = select(Game)

    # ---- 状态筛选 ----
    if status:
        if status == "listed":
            # 公开列表 = published + preview
            # Game.status.in_(["published", "preview"]) 生成: WHERE games.status IN ('published', 'preview')
            base_query = base_query.where(Game.status.in_(["published", "preview"]))
        else:
            base_query = base_query.where(Game.status == status)
    else:
        # 无 status 参数时默认也返回公开的游戏（与 listed 行为一致）
        base_query = base_query.where(Game.status.in_(["published", "preview"]))

    # ---- 标签过滤（跨数据库兼容的 JSON 搜索）----
    if tag:
        # cast(Text): 将 JSON/JSONB 列强制转为数据库的 TEXT 类型
        # .like(f'%"{tag}"%'): 使用双引号包裹搜索词，确保精确匹配
        #
        # SQLite 生成的 SQL:
        #   WHERE CAST(games.tags AS TEXT) LIKE '%"射击"%'
        #
        # PostgreSQL 生成的 SQL:
        #   WHERE CAST(games.tags AS TEXT) LIKE '%"射击"%'
        #
        # 为什么用双引号？
        #   JSON 数组格式: ["射击", "RPG", "冒险"]
        #   搜索 "射击"  → LIKE '%"射击"%' → 匹配成功
        #   搜索 "RPG"   → LIKE '%"RPG"%'  → 匹配 "RPG" 但不匹配 "ARPG" ✓
        #   搜索 "冒险"  → LIKE '%"冒险"%' → 匹配成功
        #   如果没有引号: LIKE '%RPG%' → 会误匹配 "ARPG" ✗
        #
        # 局限性:
        #   1. 如果标签本身包含双引号，会导致匹配失效（但游戏标签通常不含引号）
        #   2. 全表扫描（因为 LIKE + CAST 无法使用普通索引）
        #     解决方案: 如果标签搜索成为性能瓶颈，可以:
        #       a. 迁到 PostgreSQL 并使用 GIN 索引 + JSONB 操作符
        #       b. 加入应用层缓存（Redis）
        #       c. 改为独立标签表
        base_query = base_query.where(Game.tags.cast(Text).like(f'%"{tag}"%'))

    # ---- 计数查询（用于分页 total 字段）----
    # .subquery() 将 base_query 包装为子查询，再 SELECT COUNT(*) FROM (子查询)
    # 这样可以复用 base_query 的所有 WHERE 条件
    count_query = select(func.count()).select_from(base_query.subquery())
    total = (await db.execute(count_query)).scalar() or 0
    # `or 0`: 防御性编程 — scalar() 理论上不会返回 None（COUNT 总是返回数字），
    #         但类型标注允许 None，所以显式处理

    # ---- 分页 + 预加载关联 ----
    # 在 base_query 基础上添加 eager loading、排序、分页
    query = base_query.options(
        selectinload(Game.assets),   # 预加载资源（避免 N+1）
        selectinload(Game.author),   # 预加载作者（避免 N+1）
    )
    # 按创建时间倒序（最新的在前），OFFSET + LIMIT 分页
    query = query.order_by(Game.created_at.desc()).offset((page - 1) * size).limit(size)
    result = await db.execute(query)
    games = result.scalars().all()

    # ---- 组装响应 ----
    items = []
    for g in games:
        resp = GameResponse.model_validate(g)
        # 从关联的 User 对象获取 author_name
        if g.author:
            resp.author_name = g.author.username
        items.append(resp)

    return GameListResponse(
        items=items,
        total=total,
        page=page,
        size=size,
    )


# ============================================================================
# update_game — 更新游戏元数据
# ============================================================================
async def update_game(db: AsyncSession, game_id: str, data: GameUpdate) -> Game | None:
    """
    更新游戏元数据（标题、描述、标签等）。

    model_dump(exclude_unset=True) 的作用:
        - 只导出客户端"实际发送"的字段
        - 例如客户端发送 {"title": "新标题"}，其他字段如 description 不会被覆盖
        - 区别于 model_dump()（导出所有字段，未设置的用默认值）
        - 这是 Pydantic v2 的"部分更新"(partial update) 标准做法

    setattr 动态设置属性:
        - 避免逐字段写 if-else（如: if "title" in data: game.title = data.title）
        - 遍历 update_data 字典，动态赋值
        - 注意: 这要求 schema 字段名和 ORM 字段名完全一致
    """
    # 先查询游戏（带关联数据）+ 权限检查已在 Router 层完成
    game = await get_game(db, game_id)
    if not game:
        return None

    # 导出客户端实际发送的字段（exclude_unset=True 排除未设置的字段）
    update_data = data.model_dump(exclude_unset=True)

    # 动态设置每个字段值
    for key, value in update_data.items():
        setattr(game, key, value)

    await db.commit()
    await db.refresh(game)
    return game


# ============================================================================
# delete_game — 删除游戏
# ============================================================================
async def delete_game(db: AsyncSession, game_id: str) -> bool:
    """
    删除游戏及其关联的 assets 和 favorites。

    级联删除机制:
        SQLAlchemy ORM 模型中 relationship 的 cascade="all, delete-orphan" 配置，
        确保删除 Game 时自动删除关联的:
          - GameAsset（资源文件记录）
          - GameFavorite（收藏记录）
        数据库层面通过外键 ON DELETE CASCADE 约束保证完整性。

    注意: 这里只删数据库记录，OSS 上的实际文件不会被删除。
         如需同时删除 OSS 文件，需先查 assets、调用 storage_service.delete_file、
         再删数据库记录。
    """
    game = await get_game(db, game_id)
    if not game:
        return False
    # db.delete(game) 将对象标记为"待删除"
    # commit 时 SQLAlchemy 根据 cascade 配置自动处理关联对象
    await db.delete(game)
    await db.commit()
    return True


# ============================================================================
# add_asset — 记录资源文件
# ============================================================================
async def add_asset(
    db: AsyncSession,
    game_id: str,
    asset_type: str,      # "image" / "audio" / "reference"
    filename: str,        # 原始文件名
    oss_key: str,         # OSS 存储路径
    oss_url: str,         # OSS 公网访问 URL
    file_size: int | None = None,  # 文件大小（可能未知）
) -> GameAsset:
    """
    记录一个新的游戏资源文件到数据库。

    注意: 这个函数只负责数据库记录。实际文件上传由 storage_service.upload_file 完成。
         两者分离意味着:
         1. upload_file 失败时数据库中不会有"幽灵记录"
         2. 可以独立测试数据库操作和文件上传操作
         3. 如果将来换存储方案（如直接存数据库 blob），只需改 storage_service
    """
    asset = GameAsset(
        game_id=game_id,
        asset_type=asset_type,
        original_filename=filename,
        oss_key=oss_key,
        oss_url=oss_url,
        file_size=file_size,
    )
    db.add(asset)
    await db.commit()
    await db.refresh(asset)
    return asset


# ============================================================================
# get_assets — 获取游戏的资源列表
# ============================================================================
async def get_assets(db: AsyncSession, game_id: str) -> list[GameAsset]:
    """
    列出某个游戏的所有已上传资源。

    这是一个轻量级查询 — 不需要 eager loading（GameAsset 没有需要预加载的关联）。
    注意: 没有分页，假设单个游戏的资源数量不会很大（一般几十个以内）。
    """
    result = await db.execute(
        select(GameAsset).where(GameAsset.game_id == game_id)
    )
    # .scalars() 返回 ScalarResult，.all() 转为 list
    # 这里用 list() 包装确保结果是普通列表（而非懒加载的迭代器）
    return list(result.scalars().all())


# ============================================================================
# delete_asset — 删除资源记录
# ============================================================================
async def delete_asset(db: AsyncSession, asset_id: str) -> bool:
    """
    删除单个资源文件的数据库记录。

    注意: 不删除 OSS 上的实际文件。如需删除 OSS 文件，调用方应先:
          1. 查 asset 获取 oss_key
          2. 调 storage_service.delete_file(oss_key)
          3. 再调此函数删除数据库记录
    """
    result = await db.execute(select(GameAsset).where(GameAsset.id == asset_id))
    asset = result.scalar_one_or_none()
    if not asset:
        return False
    await db.delete(asset)
    await db.commit()
    return True
