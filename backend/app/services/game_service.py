"""Game CRUD business logic."""

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.game import Game, GameAsset
from app.models.user import User
from app.schemas.game import GameCreate, GameUpdate, GameListResponse, GameResponse


async def create_game(db: AsyncSession, author_id: str, data: GameCreate) -> Game:
    """Create a new draft game."""
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
    await db.refresh(game)
    return game


async def get_game(db: AsyncSession, game_id: str) -> Game | None:
    """Get a single game by ID, with assets and author loaded."""
    result = await db.execute(
        select(Game)
        .where(Game.id == game_id)
        .options(selectinload(Game.assets), selectinload(Game.author))
    )
    return result.scalar_one_or_none()


async def list_games(
    db: AsyncSession,
    status: str = "published",
    tag: str | None = None,
    page: int = 1,
    size: int = 12,
) -> GameListResponse:
    """List games with optional filters, paginated. Default shows published + preview."""
    base_query = select(Game)

    if status:
        if status == "listed":
            base_query = base_query.where(Game.status.in_(["published", "preview"]))
        else:
            base_query = base_query.where(Game.status == status)
    else:
        base_query = base_query.where(Game.status.in_(["published", "preview"]))

    if tag:
        base_query = base_query.where(Game.tags.contains([tag]))

    # Count
    count_query = select(func.count()).select_from(base_query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # Paginate with eager loads
    query = base_query.options(selectinload(Game.assets), selectinload(Game.author))
    query = query.order_by(Game.created_at.desc()).offset((page - 1) * size).limit(size)
    result = await db.execute(query)
    games = result.scalars().all()

    items = []
    for g in games:
        resp = GameResponse.model_validate(g)
        if g.author:
            resp.author_name = g.author.username
        items.append(resp)

    return GameListResponse(
        items=items,
        total=total,
        page=page,
        size=size,
    )


async def update_game(db: AsyncSession, game_id: str, data: GameUpdate) -> Game | None:
    """Update game metadata."""
    game = await get_game(db, game_id)
    if not game:
        return None

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(game, key, value)

    await db.commit()
    await db.refresh(game)
    return game


async def delete_game(db: AsyncSession, game_id: str) -> bool:
    """Delete a game and its assets."""
    game = await get_game(db, game_id)
    if not game:
        return False
    await db.delete(game)
    await db.commit()
    return True


async def add_asset(
    db: AsyncSession,
    game_id: str,
    asset_type: str,
    filename: str,
    oss_key: str,
    oss_url: str,
    file_size: int | None = None,
) -> GameAsset:
    """Record a new game asset."""
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


async def get_assets(db: AsyncSession, game_id: str) -> list[GameAsset]:
    """List all assets for a game."""
    result = await db.execute(
        select(GameAsset).where(GameAsset.game_id == game_id)
    )
    return list(result.scalars().all())


async def delete_asset(db: AsyncSession, asset_id: str) -> bool:
    """Delete a single asset."""
    result = await db.execute(select(GameAsset).where(GameAsset.id == asset_id))
    asset = result.scalar_one_or_none()
    if not asset:
        return False
    await db.delete(asset)
    await db.commit()
    return True
