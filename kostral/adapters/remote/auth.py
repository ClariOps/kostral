"""Bearer-token authentication between the client and a remote engine server.

The token is a shared secret. It is never written in a registry file or in the
repository: each side reads it from an environment variable whose NAME is
configured. Every request must carry it, and a missing or weak token is an error,
never a fallback to "no authentication".
"""
import hmac
import os
import re
from urllib.parse import urlparse

MIN_TOKEN_LENGTH = 16
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
_ENV_NAME = re.compile(r"[A-Z_][A-Z0-9_]*")


def check_env_name(name, who):
    """token_env must be the NAME of a variable. A pasted token is rejected, and
    never repeated in the message."""
    if not isinstance(name, str) or not _ENV_NAME.fullmatch(name):
        raise ValueError(
            f"{who}: token_env must be the NAME of an environment variable "
            f"(like KOSTRAL_TOKEN_OPTIMIZER), never the token itself")
    return name


def read_token(env_name, who):
    """Read the shared secret from the environment. Missing or weak is an error."""
    token = os.environ.get(env_name, "")
    if not token:
        raise ValueError(f"{who}: environment variable {env_name} is not set")
    if len(token) < MIN_TOKEN_LENGTH:
        raise ValueError(f"{who}: the token in {env_name} is shorter than {MIN_TOKEN_LENGTH} characters")
    return token


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def is_authorized(header, expected):
    """Constant-time check of an Authorization header against the expected token."""
    prefix = "Bearer "
    provided = header[len(prefix):] if isinstance(header, str) and header.startswith(prefix) else ""
    return hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))


def check_transport(url, who):
    """A token may only travel over https, or over http to this machine."""
    parsed = urlparse(url)
    if parsed.scheme == "https":
        return
    if parsed.scheme == "http" and parsed.hostname in _LOOPBACK_HOSTS:
        return
    raise ValueError(
        f"{who}: refusing to send a token over plain http to '{parsed.hostname}'; "
        f"use https (plain http is only allowed to localhost)")