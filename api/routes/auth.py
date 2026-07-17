from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
import jwt
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.database import get_db
from api.models import User

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=False)

COOKIE_NAME = "access_token"


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 480


class Token(BaseModel):
    access_token: str
    token_type: str
    role: str
    username: str


def create_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.secret_key, algorithm=ALGORITHM)


@router.post("/token", response_model=Token)
async def login(
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.username == form_data.username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales incorrectas",
        )
    token = create_token({"sub": user.username, "role": user.role})
    # Defensa en profundidad: además del token en el body (usado por el
    # frontend actual vía Authorization header y por scripts/demo_flow.py),
    # se setea una cookie httpOnly — no accesible desde JS, mitiga robo de
    # token por XSS. get_current_user() acepta cualquiera de las dos vías.
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.environment == "production",
        samesite="lax",
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )
    return Token(access_token=token, token_type="bearer", role=user.role, username=user.username)


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"status": "logged_out"}


async def get_current_user(
    request: Request,
    token: str | None = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Verifica el JWT (Authorization: Bearer o cookie httpOnly) y retorna el
    usuario. Antes NINGÚN endpoint verificaba el token — se emitía en /token
    pero oauth2_scheme nunca se usaba como dependencia en ninguna ruta, así
    que toda la API era efectivamente anónima. Se aplica ahora a los routers
    que solo sirve el dashboard (clients, itinerary, monitoring, stats) —
    los routers que también reciben tráfico interno de los agentes
    (packages, quotations, reservations, liquidations, sagas, documents,
    validation-logs, knowledge, agent-interactions) quedan pendientes de una
    estrategia de auth servicio-a-servicio separada (ver docs/architecture.md,
    sección de seguridad) para no romper la comunicación entre agentes."""
    if not token:
        token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No autenticado",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if not username:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token inválido")
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )

    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuario no encontrado o inactivo")
    return user


@router.get("/me")
async def read_current_user(user: User = Depends(get_current_user)):
    return {"username": user.username, "role": user.role, "email": user.email}
