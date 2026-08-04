# auth.py

import os
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jwt import decode, encode
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import SessionDep
from models import (
    BlacklistedToken,
    UserModel,  # SQLAlchemy-модель
)


# ---------- Pydantic-модели ----------
class UserBase(BaseModel):
    username: str
    email: str | None = None
    full_name: str | None = None
    role: str = "user"


class UserCreate(UserBase):
    password: str


class User(UserBase):
    id: UUID
    disabled: bool | None = None
    # поля, которые возвращаем клиенту (без hashed_password)

    model_config = ConfigDict(from_attributes=True)


class UserInDB(User):
    hashed_password: str
    created_at: datetime


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str


class TokenData(BaseModel):
    username: str | None = None


# ---------- Конфигурация JWT ----------

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30


def _get_secret_key() -> str:
    """Ленивая загрузка SECRET_KEY при первом использовании."""
    key = os.getenv("SECRET_KEY")
    if not key:
        raise ValueError("SECRET_KEY must be set in environment")
    return key


# ---------- Хеширование паролей ----------
password_hash = PasswordHash.recommended()
DUMMY_HASH = password_hash.hash("dummypassword")


def get_password_hash(password: str) -> str:
    return password_hash.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return password_hash.verify(plain_password, hashed_password)


# ---------- Работа с БД ----------
async def get_user(username: str, session: AsyncSession) -> UserInDB | None:
    result = await session.execute(
        select(UserModel).where(UserModel.username == username)
    )
    user = result.scalar_one_or_none()
    if user is None:
        return None
    # Преобразуем ORM-объект в Pydantic-схему
    return UserInDB(
        id=user.id,
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        disabled=user.disabled,
        role=user.role,
        hashed_password=user.hashed_password,
        created_at=user.created_at,
    )


async def authenticate_user(username: str, password: str, session: AsyncSession) -> UserInDB | None:
    user = await get_user(username, session)
    if not user:
        # защита от timing-атаки
        verify_password(password, DUMMY_HASH)
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


# ---------- JWT ----------
REFRESH_TOKEN_EXPIRE_DAYS = 30   # или 7


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(minutes=15)
    to_encode.update({"exp": expire, "type": "access"})
    return encode(to_encode, _get_secret_key(), algorithm=ALGORITHM)


def create_refresh_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return encode(to_encode, _get_secret_key(), algorithm=ALGORITHM)


def get_user_permissions(role: str) -> list:
    """Получить список разрешений для роли пользователя."""
    permissions_map = {
        "user": [
            "items:read",
            "items:create",
            "items:update:own",
            "items:delete:own",
            "profile:read",
            "profile:update",
        ],
        "moderator": [
            "items:read",
            "items:create",
            "items:update:any",
            "items:delete:any",
            "profile:read",
            "profile:update",
            "users:read",
            "users:update",
        ],
        "admin": [
            "items:read",
            "items:create",
            "items:update:any",
            "items:delete:any",
            "profile:read",
            "profile:update",
            "users:read",
            "users:create",
            "users:update",
            "users:delete",
            "users:role",
            "system:config",
        ],
    }
    return permissions_map.get(role, permissions_map["user"])


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


async def get_token_from_request(request: Request) -> str:
    """Извлечь Bearer-токен из заголовка Authorization."""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return auth_header[7:]  # Убираем префикс "Bearer "


async def get_current_user_stateless(
    _request: Request,
    token: Annotated[str, Depends(get_token_from_request)],
) -> dict:
    """
    Stateless-проверка токена без обращения к БД.
    Данные извлекаются напрямую из payload JWT.
    Подходит для микросервисной архитектуры, где каждый сервис
    проверяет токен самостоятельно.

    Возвращает словарь c полями: sub, user_id, role, email, type, exp.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode(token, _get_secret_key(), algorithms=[ALGORITHM])
        token_type = payload.get("type")
        if token_type not in ("access", "refresh"):
            raise credentials_exception
        username = payload.get("sub")
        if username is None:
            raise credentials_exception
    except InvalidTokenError as exc:
        raise credentials_exception from exc

    # Извлекаем все нужные поля с дефолтными значениями
    user_data = {
        "sub": username,
        "user_id": payload.get("user_id"),
        "role": payload.get("role", "user"),
        "email": payload.get("email"),
        "type": token_type,
    }
    return user_data


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    session: SessionDep,
) -> UserInDB:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode(token, _get_secret_key(), algorithms=[ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except InvalidTokenError as exc:
        raise credentials_exception from exc

    blacklisted = await session.execute(
        select(BlacklistedToken).where(BlacklistedToken.token == token)
    )
    if blacklisted.scalar_one_or_none() is not None:
        raise credentials_exception
    assert token_data.username is not None

    user = await get_user(token_data.username, session)
    if user is None:
        raise credentials_exception
    return user


async def get_current_active_user(
    current_user: Annotated[UserInDB, Depends(get_current_user)]
) -> UserInDB:
    if current_user.disabled is True:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
        )
    return current_user
