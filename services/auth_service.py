from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt


@dataclass(frozen=True)
class AuthUser:
    id: str
    email: str
    password_hash: str
    role: str


@dataclass(frozen=True)
class AuthSession:
    token: str
    user_id: str
    email: str
    expires_at_iso: str
    role: str


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class AuthService:
    def __init__(self, db=None):
        self._db = db
        default_email = os.environ.get("REVIEWDATA_DEFAULT_EMAIL", "admin@reviewdata.local").strip()
        default_password = os.environ.get("REVIEWDATA_DEFAULT_PASSWORD", "admin123")
        seed_user_email = os.environ.get("REVIEWDATA_SEED_USER_EMAIL", "user@reviewdata.local").strip()
        seed_user_password = os.environ.get("REVIEWDATA_SEED_USER_PASSWORD", "user123")
        self._fallback_users_by_email: dict[str, AuthUser] = {
            default_email.lower(): AuthUser(id="1", email=default_email, password_hash=_sha256(default_password), role="admin"),
            seed_user_email.lower(): AuthUser(id="2", email=seed_user_email, password_hash=_sha256(seed_user_password), role="user"),
        }
        self._jwt_secret = os.environ.get("REVIEWDATA_JWT_SECRET", "reviewdata-dev-secret")
        self._jwt_issuer = "reviewdata"

    def authenticate(self, email: str, password: str) -> AuthSession | None:
        e = (email or "").strip().lower()
        if not e:
            return None
        user: AuthUser | None = None
        if self._db and getattr(self._db, "conn", None):
            rows = self._db.fetch_all(
                "SELECT id, email, password_hash, role FROM users WHERE lower(email) = lower(%s) AND active = TRUE",
                (email,),
            )
            if rows:
                r = rows[0]
                user = AuthUser(
                    id=str(r.get("id", "")),
                    email=str(r.get("email", "")),
                    password_hash=str(r.get("password_hash", "")),
                    role=str(r.get("role", "user")) or "user",
                )
        else:
            user = self._fallback_users_by_email.get(e)
        if not user or user.password_hash != _sha256(password or ""):
            return None
        now = datetime.now(timezone.utc)
        exp = now + timedelta(hours=8)
        payload = {
            "sub": user.id,
            "email": user.email,
            "role": user.role,
            "iss": self._jwt_issuer,
            "iat": int(now.timestamp()),
            "exp": int(exp.timestamp()),
        }
        token = jwt.encode(payload, self._jwt_secret, algorithm="HS256")
        return AuthSession(token=token, user_id=user.id, email=user.email, expires_at_iso=exp.isoformat(), role=user.role)

    def verify_token(self, token: str) -> AuthSession | None:
        if not token:
            return None
        try:
            payload = jwt.decode(token, self._jwt_secret, algorithms=["HS256"], issuer=self._jwt_issuer)
            user_id = str(payload.get("sub", ""))
            email = str(payload.get("email", ""))
            role = str(payload.get("role", "user")) or "user"
            exp_ts = int(payload.get("exp", 0))
            exp = datetime.fromtimestamp(exp_ts, tz=timezone.utc)
            return AuthSession(token=token, user_id=user_id, email=email, expires_at_iso=exp.isoformat(), role=role)
        except Exception:
            return None
