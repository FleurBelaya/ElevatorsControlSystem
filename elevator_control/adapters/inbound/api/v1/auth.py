from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm

from elevator_control.adapters.inbound.api import schemas
from elevator_control.adapters.inbound.api.deps import AuthSvcDep, CurrentUserDep

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=schemas.UserRead, status_code=status.HTTP_201_CREATED)
async def register_user(auth_svc: AuthSvcDep, body: schemas.UserRegister) -> schemas.UserRead:
    # 2.1 Авторизация RBAC
    # 3.2 Разные клиенты — разные сценарии: регистрация с учетом роли.
    user = await auth_svc.register(body.email, body.password, role=body.role, admin_code=body.admin_code)
    return schemas.UserRead(id=user.id, email=user.email, roles=user.roles)


@router.post("/login", response_model=schemas.TokenResponse)
async def login(
    auth_svc: AuthSvcDep,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> schemas.TokenResponse:
    # 2.1 Авторизация RBAC
    token = await auth_svc.login(form_data.username, form_data.password)
    return schemas.TokenResponse(access_token=token.access_token, token_type=token.token_type)


@router.post("/login-json", response_model=schemas.TokenResponse)
async def login_json(auth_svc: AuthSvcDep, body: schemas.UserLogin) -> schemas.TokenResponse:
    # 2.1 Авторизация RBAC
    token = await auth_svc.login(body.email, body.password)
    return schemas.TokenResponse(access_token=token.access_token, token_type=token.token_type)


@router.get("/me", response_model=schemas.UserRead)
async def me(current_user: CurrentUserDep) -> schemas.UserRead:
    # 2.1 Авторизация RBAC
    return schemas.UserRead(id=current_user.id, email=current_user.email, roles=current_user.roles)
