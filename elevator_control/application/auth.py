from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from elevator_control.domain import auth as domain_auth
from elevator_control.domain.exceptions import ConflictError, ForbiddenError, UnauthorizedError
from elevator_control.ports.outbound import repositories as r


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(data: str) -> bytes:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def hash_password(password: str, *, iterations: int = 200_000) -> str:
    # 2.1 Авторизация RBAC
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${_b64url_encode(salt)}${_b64url_encode(dk)}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        scheme, iterations_s, salt_s, hash_s = password_hash.split("$", 3)
    except ValueError:
        return False
    if scheme != "pbkdf2_sha256":
        return False
    try:
        iterations = int(iterations_s)
    except ValueError:
        return False
    salt = _b64url_decode(salt_s)
    expected = _b64url_decode(hash_s)
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


def _new_jti() -> str:
    # 6.2.3 Logout: уникальный идентификатор токена (JWT ID) для blacklist.
    return secrets.token_urlsafe(24)


def create_token(*, user_id: int, secret_key: str, expires_in_seconds: int, token_kind: str) -> tuple[str, str, int]:
    # 6.2.1 / 6.2.2 / 6.2.3: общий конструктор JWT для access и refresh токенов.
    # Возвращает (token, jti, exp) — exp нужен для blacklist (TTL).
    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    exp = now + int(expires_in_seconds)
    jti = _new_jti()
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": exp,
        "jti": jti,
        "type": token_kind,
    }
    header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    sig = hmac.new(secret_key.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{header_b64}.{payload_b64}.{_b64url_encode(sig)}", jti, exp


def decode_token(token: str, *, secret_key: str) -> dict:
    # 2.1 Авторизация RBAC + 6.2.1 проверка срока жизни.
    try:
        header_b64, payload_b64, sig_b64 = token.split(".", 2)
    except ValueError as exc:
        raise UnauthorizedError("Некорректный токен") from exc
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    expected_sig = hmac.new(secret_key.encode("utf-8"), signing_input, hashlib.sha256).digest()
    try:
        got_sig = _b64url_decode(sig_b64)
    except Exception as exc:  # noqa: BLE001
        raise UnauthorizedError("Некорректный токен") from exc
    if not hmac.compare_digest(got_sig, expected_sig):
        raise UnauthorizedError("Некорректный токен")
    try:
        payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise UnauthorizedError("Некорректный токен") from exc
    exp = payload.get("exp")
    if not isinstance(exp, int) or exp < int(time.time()):
        raise UnauthorizedError("Токен истёк")
    return payload


# Совместимость со старым кодом
def create_access_token(*, user_id: int, secret_key: str, expires_in_seconds: int) -> str:
    token, _jti, _exp = create_token(
        user_id=user_id,
        secret_key=secret_key,
        expires_in_seconds=expires_in_seconds,
        token_kind="access",
    )
    return token


def decode_access_token(token: str, *, secret_key: str) -> dict:
    return decode_token(token, secret_key=secret_key)


@dataclass(slots=True)
class TokenPair:
    # 6.2.2 Refresh: при логине отдаём пару access+refresh.
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AuthorizationService:
    # 2.1 Авторизация RBAC
    def __init__(self, repo: r.AuthRepository) -> None:
        self._repo = repo
        self._perm_cache: dict[int, set[str]] = {}

    async def permissions(self, user_id: int) -> set[str]:
        cached = self._perm_cache.get(user_id)
        if cached is not None:
            return cached
        perms = await self._repo.list_permission_names_for_user(user_id)
        self._perm_cache[user_id] = perms
        return perms

    async def require(self, user_id: int, permission: str) -> None:
        perms = await self.permissions(user_id)
        if permission not in perms:
            raise ForbiddenError("Недостаточно прав")

    async def can_bypass_ownership(self, user_id: int) -> bool:
        perms = await self.permissions(user_id)
        return "ownership:bypass" in perms


class AuthApplicationService:
    # 2.1 Авторизация RBAC + 6.2 JWT (TTL/refresh/logout/blacklist)
    def __init__(
        self,
        repo: r.AuthRepository,
        session: AsyncSession,
        *,
        jwt_secret_key: str,
        access_token_ttl_seconds: int,
        refresh_token_ttl_seconds: int = 7 * 24 * 60 * 60,
        admin_role_name: str = "administrator",
        default_role_name: str = "dispatcher",
        registration_admin_code: str | None = None,
    ) -> None:
        self._repo = repo
        self._session = session
        self._jwt_secret_key = jwt_secret_key
        self._access_token_ttl_seconds = access_token_ttl_seconds
        self._refresh_token_ttl_seconds = refresh_token_ttl_seconds
        self._admin_role_name = admin_role_name
        self._default_role_name = default_role_name
        self._registration_admin_code = registration_admin_code

    async def register(
        self,
        email: str,
        password: str,
        *,
        role: str | None = None,
        admin_code: str | None = None,
    ) -> domain_auth.User:
        # 6.1.1 Валидация на уровне Pydantic; здесь — бизнес-проверки.
        existing = await self._repo.get_user_credentials_by_email(email)
        if existing is not None:
            raise ConflictError("Пользователь уже существует")
        user = await self._repo.create_user(email, hash_password(password))
        is_first = (await self._repo.count_users()) == 1

        resolved_role = self._admin_role_name if is_first else (role or self._default_role_name)
        allowed_roles = {self._default_role_name, "technician", self._admin_role_name}
        if resolved_role not in allowed_roles:
            raise ConflictError("Unknown role")

        if resolved_role == self._admin_role_name and not is_first:
            expected = self._registration_admin_code
            if expected is None:
                expected = os.getenv("ELEVATOR_REGISTRATION_ADMIN_CODE") or os.getenv(
                    "REGISTRATION_ADMIN_CODE"
                )
            if expected is None or admin_code != expected:
                raise ForbiddenError("Admin registration is not allowed")

        await self._repo.assign_role_to_user(user.id, resolved_role)
        refreshed = await self._repo.get_user_by_id(user.id)
        assert refreshed is not None
        return refreshed

    async def login(self, email: str, password: str) -> TokenPair:
        # 6.2.1 access TTL + 6.2.2 refresh TTL
        user = await self._repo.get_user_credentials_by_email(email)
        if user is None or not user.is_active:
            raise UnauthorizedError("Неверный логин или пароль")
        if not verify_password(password, user.password_hash):
            raise UnauthorizedError("Неверный логин или пароль")
        access, _jti_a, _exp_a = create_token(
            user_id=user.id,
            secret_key=self._jwt_secret_key,
            expires_in_seconds=self._access_token_ttl_seconds,
            token_kind="access",
        )
        refresh, _jti_r, _exp_r = create_token(
            user_id=user.id,
            secret_key=self._jwt_secret_key,
            expires_in_seconds=self._refresh_token_ttl_seconds,
            token_kind="refresh",
        )
        return TokenPair(access_token=access, refresh_token=refresh)

    async def refresh(self, refresh_token: str) -> TokenPair:
        # 6.2.2 Refresh: меняем refresh-токен на новую пару.
        payload = decode_token(refresh_token, secret_key=self._jwt_secret_key)
        if payload.get("type") != "refresh":
            raise UnauthorizedError("Это не refresh-токен")
        jti = payload.get("jti")
        if not isinstance(jti, str):
            raise UnauthorizedError("Некорректный refresh-токен")
        # 6.2.3 blacklist: если jti уже отозван, отказываем.
        if await self._is_revoked(jti):
            raise UnauthorizedError("Refresh-токен отозван")
        try:
            user_id = int(payload.get("sub"))
        except Exception as exc:  # noqa: BLE001
            raise UnauthorizedError("Некорректный refresh-токен") from exc
        user = await self._repo.get_user_by_id(user_id)
        if user is None:
            raise UnauthorizedError("Пользователь не найден")
        # 6.2.3 Rotation: помечаем старый refresh как использованный.
        await self._revoke(jti, user_id, int(payload["exp"]))
        access, _jti_a, _exp_a = create_token(
            user_id=user_id,
            secret_key=self._jwt_secret_key,
            expires_in_seconds=self._access_token_ttl_seconds,
            token_kind="access",
        )
        new_refresh, _jti_r, _exp_r = create_token(
            user_id=user_id,
            secret_key=self._jwt_secret_key,
            expires_in_seconds=self._refresh_token_ttl_seconds,
            token_kind="refresh",
        )
        return TokenPair(access_token=access, refresh_token=new_refresh)

    async def logout(self, access_token: str) -> None:
        # 6.2.3 Logout: помещаем jti в blacklist до истечения TTL токена.
        payload = decode_token(access_token, secret_key=self._jwt_secret_key)
        jti = payload.get("jti")
        if not isinstance(jti, str):
            return
        try:
            user_id = int(payload.get("sub"))
        except Exception:  # noqa: BLE001
            return
        await self._revoke(jti, user_id, int(payload["exp"]))

    async def get_user_from_access_token(self, token: str) -> domain_auth.User:
        # 6.2.1 + 6.2.3: проверяем подпись/TTL и blacklist.
        payload = decode_token(token, secret_key=self._jwt_secret_key)
        if payload.get("type") not in (None, "access"):
            raise UnauthorizedError("Ожидался access-токен")
        jti = payload.get("jti")
        if isinstance(jti, str) and await self._is_revoked(jti):
            raise UnauthorizedError("Токен отозван")
        try:
            user_id = int(payload.get("sub"))
        except Exception as exc:  # noqa: BLE001
            raise UnauthorizedError("Некорректный токен") from exc
        user = await self._repo.get_user_by_id(user_id)
        if user is None:
            raise UnauthorizedError("Пользователь не найден")
        return user

    # Старое имя — оставлено для обратной совместимости.
    async def get_user_from_token(self, token: str) -> domain_auth.User:
        return await self.get_user_from_access_token(token)

    async def _is_revoked(self, jti: str) -> bool:
        # 6.2.3 blacklist через таблицу revoked_tokens (см. миграцию 003).
        row = (
            await self._session.execute(
                text("SELECT 1 FROM revoked_tokens WHERE jti = :jti"),
                {"jti": jti},
            )
        ).first()
        return row is not None

    async def _revoke(self, jti: str, user_id: int, exp_unix: int) -> None:
        expires_at = datetime.fromtimestamp(int(exp_unix), tz=timezone.utc)
        await self._session.execute(
            text(
                """
                INSERT INTO revoked_tokens (jti, user_id, expires_at)
                VALUES (:jti, :user_id, :expires_at)
                ON CONFLICT (jti) DO NOTHING
                """
            ),
            {"jti": jti, "user_id": user_id, "expires_at": expires_at},
        )
