"""Offline password hash generation: python -m app.password (no database or settings imports)."""

import getpass
import hashlib
import secrets

ITERATIONS = 600_000


def hash_password(password: str) -> str:
    if not 15 <= len(password) <= 1024:
        raise ValueError("use a password of 15 to 1024 characters")
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), ITERATIONS).hex()
    return f"pbkdf2_sha256${ITERATIONS}${salt}${digest}"


def verify_password(password: str, encoded: str) -> bool:
    _, iterations, salt, expected = encoded.split("$")
    try:
        raw = password.encode()
    except UnicodeError:
        return False
    actual = hashlib.pbkdf2_hmac("sha256", raw, bytes.fromhex(salt), int(iterations)).hex()
    return secrets.compare_digest(actual, expected)


if __name__ == "__main__":
    password = getpass.getpass("Owner password (at least 15 characters): ")
    if password != getpass.getpass("Confirm password: "):
        raise SystemExit("Passwords do not match")
    try:
        print(hash_password(password))
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
