import os
from functools import lru_cache, wraps

import jwt
from flask import g, jsonify, request
from jwt import PyJWKClient


@lru_cache(maxsize=1)
def _jwks_client() -> PyJWKClient:
    ref = os.environ["SUPABASE_PROJECT_REF"]
    return PyJWKClient(
        f"https://{ref}.supabase.co/auth/v1/.well-known/jwks.json",
        cache_keys=True,
    )


def _decode_token(token: str) -> dict:
    signing_key = _jwks_client().get_signing_key_from_jwt(token)
    return jwt.decode(
        token,
        signing_key.key,
        algorithms=["ES256", "RS256"],
        audience="authenticated",
    )


def require_auth(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return jsonify({"error": "missing_or_invalid_authorization"}), 401

        token = header[len("Bearer ") :].strip()
        try:
            payload = _decode_token(token)
        except jwt.PyJWTError as exc:
            return jsonify({"error": "invalid_token", "detail": str(exc)}), 401

        g.user_id = payload["sub"]
        g.jwt = token
        return fn(*args, **kwargs)

    return wrapper
