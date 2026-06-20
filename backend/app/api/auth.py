"""Authentication API routes."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.user import UserCreate, UserLogin, UserResponse, TokenResponse
from app.schemas.game import GameResponse
from app.services.auth_service import register_user, login_user, AuthError
from app.api.deps import get_current_user
from app.models.user import User
from app.models.game import GameFavorite, Game

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(data: UserCreate, db: AsyncSession = Depends(get_db)):
    """Register a new user account. Returns JWT token and user info."""
    try:
        return await register_user(db, data)
    except AuthError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.post("/login", response_model=TokenResponse)
async def login(data: UserLogin, db: AsyncSession = Depends(get_db)):
    """Login with email and password. Returns JWT token and user info."""
    try:
        return await login_user(db, data.email, data.password)
    except AuthError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Get the currently authenticated user's profile."""
    return UserResponse.model_validate(current_user)


@router.get("/me/favorites", response_model=list[str])
async def get_my_favorite_ids(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Get IDs of games favorited by the current user."""
    result = await db.execute(
        select(GameFavorite.game_id).where(GameFavorite.user_id == current_user.id)
    )
    return [row[0] for row in result.all()]
