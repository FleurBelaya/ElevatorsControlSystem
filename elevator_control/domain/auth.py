from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class User:
    id: int
    email: str
    roles: list[str]


@dataclass(slots=True)
class UserCredentials:
    id: int
    email: str
    password_hash: str
    is_active: bool
