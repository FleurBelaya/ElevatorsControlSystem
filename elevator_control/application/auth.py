from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass

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


def create_access_token(*, user_id: int, secret_key: str, expires_in_seconds: int) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    payload = {"sub": str(user_id), "iat": now, "exp": now + int(expires_in_seconds)}
    header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    sig = hmac.new(secret_key.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{header_b64}.{payload_b64}.{_b64url_encode(sig)}"


def decode_access_token(token: str, *, secret_key: str) -> dict:
    # 2.1 Авторизация RBAC
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


@dataclass(slots=True)
class TokenPair:
    access_token: str
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
    # 2.1 Авторизация RBAC
    def __init__(
        self,
        repo: r.AuthRepository,
        *,
        jwt_secret_key: str,
        access_token_ttl_seconds: int,
        admin_role_name: str = "administrator",
        default_role_name: str = "dispatcher",
        registration_admin_code: str | None = None,
    ) -> None:
        self._repo = repo
        self._jwt_secret_key = jwt_secret_key
        self._access_token_ttl_seconds = access_token_ttl_seconds
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
        # 3.2 Разные клиенты — разные сценарии:
        # регистрация с учетом роли (dispatcher/technician/administrator).
        existing = await self._repo.get_user_credentials_by_email(email)
        if existing is not None:
            raise ConflictError("Пользователь уже существует")
        user = await self._repo.create_user(email, hash_password(password))
        is_first = (await self._repo.count_users()) == 1

        resolved_role = self._admin_role_name if is_first else (role or self._default_role_name)
        allowed_roles = {self._default_role_name, "technician", self._admin_role_name}
        if resolved_role not in allowed_roles:
            raise ConflictError("Unknown role")

        # 3.2 Разные клиенты — разные сценарии (MVP-безопасность):
        # администратора можно зарегистрировать только если это первый пользователь ИЛИ если указан общий код.
        if resolved_role == self._admin_role_name and not is_first:
            expected = self._registration_admin_code
            if expected is None:
                expected = os.getenv("ELEVATOR_REGISTRATION_ADMIN_CODE") or os.getenv("REGISTRATION_ADMIN_CODE")
            if expected is None or admin_code != expected:
                raise ForbiddenError("Admin registration is not allowed")

        await self._repo.assign_role_to_user(user.id, resolved_role)
        refreshed = await self._repo.get_user_by_id(user.id)
        assert refreshed is not None
        return refreshed

    async def login(self, email: str, password: str) -> TokenPair:
        user = await self._repo.get_user_credentials_by_email(email)
        if user is None or not user.is_active:
            raise UnauthorizedError("Неверный логин или пароль")
        if not verify_password(password, user.password_hash):
            raise UnauthorizedError("Неверный логин или пароль")
        token = create_access_token(
            user_id=user.id,
            secret_key=self._jwt_secret_key,
            expires_in_seconds=self._access_token_ttl_seconds,
        )
        return TokenPair(access_token=token)

    async def get_user_from_token(self, token: str) -> domain_auth.User:
        payload = decode_access_token(token, secret_key=self._jwt_secret_key)
        sub = payload.get("sub")
        try:
            user_id = int(sub)
        except Exception as exc:  # noqa: BLE001
            raise UnauthorizedError("Некорректный токен") from exc
        user = await self._repo.get_user_by_id(user_id)
        if user is None:
            raise UnauthorizedError("Пользователь не найден")
        return user
