from hashlib import scrypt
from hmac import compare_digest
from secrets import token_bytes


def derive(password: str, salt: bytes) -> bytes:
    return scrypt(
        password.encode(), salt=salt, n=2**15, r=8, p=3, maxmem=64 * 1024 * 1024
    )


def hash_password(password: str) -> str:
    salt = token_bytes(16)
    return f"{salt.hex()}:{derive(password, salt).hex()}"


def verify_password(password: str, encoded: str | None) -> bool:
    salt, expected = bytes(16), bytes(64)
    if encoded is not None:
        try:
            salt_hex, hash_hex = encoded.split(":")
            salt, expected = bytes.fromhex(salt_hex), bytes.fromhex(hash_hex)
            if len(salt) != 16 or len(expected) != 64:
                return False
        except ValueError:
            return False
    matches = compare_digest(derive(password, salt), expected)
    return encoded is not None and matches
