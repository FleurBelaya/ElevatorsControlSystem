from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm

from elevator_control.adapters.inbound.api import schemas
from elevator_control.adapters.inbound.api.deps import AuthSvcDep, CurrentUserDep, TokenDep

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=schemas.UserRead, status_code=status.HTTP_201_CREATED)
async def register_user(auth_svc: AuthSvcDep, body: schemas.UserRegister) -> schemas.UserRead:
    # 6.1.1 Валидация: длина email/пароля проверяется Pydantic.
    # 6.1.2 Mass Assignment: модель UserRegister не содержит roles/permissions —
    # роль решается серверной логикой (admin_code/первый пользователь).
    user = await auth_svc.register(body.email, body.password, role=body.role, admin_code=body.admin_code)
    return schemas.UserRead(id=user.id, email=user.email, roles=user.roles)


@router.post("/login", response_model=schemas.TokenResponse)
async def login(
    auth_svc: AuthSvcDep,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> schemas.TokenResponse:
    # 6.2.1 Короткий TTL access + 6.2.2 отдельный refresh-токен.
    token = await auth_svc.login(form_data.username, form_data.password)
    return schemas.TokenResponse(
        access_token=token.access_token,
        refresh_token=token.refresh_token,
        token_type=token.token_type,
    )


@router.post("/login-json", response_model=schemas.TokenResponse)
async def login_json(auth_svc: AuthSvcDep, body: schemas.UserLogin) -> schemas.TokenResponse:
    token = await auth_svc.login(body.email, body.password)
    return schemas.TokenResponse(
        access_token=token.access_token,
        refresh_token=token.refresh_token,
        token_type=token.token_type,
    )


@router.post("/refresh", response_model=schemas.TokenResponse)
async def refresh_token(auth_svc: AuthSvcDep, body: schemas.RefreshRequest) -> schemas.TokenResponse:
    # 6.2.2 Refresh: меняет refresh-токен на новую пару.
    # 6.2.3 Старый refresh попадает в blacklist (rotation).
    pair = await auth_svc.refresh(body.refresh_token)
    return schemas.TokenResponse(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        token_type=pair.token_type,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(auth_svc: AuthSvcDep, token: TokenDep) -> None:
    # 6.2.3 Logout: помещаем jti токена в blacklist до его естественного истечения.
    if token:
        await auth_svc.logout(token)


@router.get("/me", response_model=schemas.UserRead)
async def me(current_user: CurrentUserDep) -> schemas.UserRead:
    return schemas.UserRead(id=current_user.id, email=current_user.email, roles=current_user.roles)
