"""Encrypted secrets storage using Fernet."""

from __future__ import annotations

from pathlib import Path

from cryptography.fernet import Fernet

from backend.models.config import AlfredSecrets


def ensure_encryption_key(key_path: Path) -> bytes:
    if key_path.exists():
        return key_path.read_bytes().strip()
    key = Fernet.generate_key()
    key_path.write_bytes(key)
    try:
        key_path.chmod(0o600)
    except OSError:
        pass
    return key


def encrypt_secrets(secrets_obj: AlfredSecrets, dest: Path, key_path: Path) -> None:
    key = ensure_encryption_key(key_path)
    fernet = Fernet(key)
    payload = secrets_obj.model_dump_json().encode()
    dest.write_bytes(fernet.encrypt(payload))


def decrypt_secrets(src: Path, key_path: Path) -> AlfredSecrets:
    key = ensure_encryption_key(key_path)
    fernet = Fernet(key)
    raw = fernet.decrypt(src.read_bytes())
    return AlfredSecrets.model_validate_json(raw)
