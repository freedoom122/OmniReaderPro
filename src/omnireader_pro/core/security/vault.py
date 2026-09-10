"""Secure document vault.

Design (documented honestly in SECURITY.md):

* Encryption: AES-256-GCM (authenticated) from the ``cryptography`` package.
* Key derivation: PBKDF2-HMAC-SHA256, 600,000 iterations (OWASP 2023
  recommendation), 16-byte random salt per vault, per-document nonce.
* The derived key is held only in memory while the vault is unlocked and
  zeroized on lock. The password is never stored anywhere.
* Argon2id would be preferable but has no dependable Windows wheel for
  Python 3.13 at the time of writing; PBKDF2 at this iteration count is the
  standard-library-verifiable fallback (see DECISIONS.md).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
import struct
import time
from pathlib import Path

from omnireader_pro.utils.safeio import atomic_write_bytes, secure_delete

logger = logging.getLogger("omnireader.vault")

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    HAS_CRYPTO = True
except ImportError:  # pragma: no cover
    HAS_CRYPTO = False

PBKDF2_ITERATIONS = 600_000
SALT_SIZE = 16
NONCE_SIZE = 12
HEADER = b"ORVAULT1"
KDF_ID_PBKDF2 = 1

VAULT_EXPIRY_SOFTLOCK = False  # no fake features; autolock handled by UI timer


class VaultError(Exception):
    pass


class VaultLockedError(VaultError):
    pass


class InvalidPasswordError(VaultError):
    pass


def derive_key(password: str, salt: bytes, iterations: int = PBKDF2_ITERATIONS) -> bytes:
    """Derive a 256-bit key from a password using PBKDF2-HMAC-SHA256."""
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, iterations, dklen=32)


def _zeroize(buf: bytearray | None) -> None:
    if buf is not None:
        for i in range(len(buf)):
            buf[i] = 0


class Vault:
    """An encrypted folder-backed vault.

    Layout on disk:
      vault/
        vault.dat    -- header + salt + kdf params
        items/
          <uuid>.oritem   -- per-item encrypted file
        index.oridx      -- encrypted index of item names
    """

    def __init__(self, directory: Path) -> None:
        if not HAS_CRYPTO:
            raise VaultError("The 'cryptography' package is required for the vault")
        self.dir = Path(directory)
        self.items_dir = self.dir / "items"
        self._dat = self.dir / "vault.dat"
        self._index = self.dir / "index.oridx"
        self._key: bytearray | None = None
        self._salt: bytes = b""
        self._iterations = PBKDF2_ITERATIONS
        self.locked = True

    # -- lifecycle --------------------------------------------------------
    def exists(self) -> bool:
        return self._dat.exists()

    def create(self, password: str) -> None:
        if self.exists():
            raise VaultError("A vault already exists here")
        self.dir.mkdir(parents=True, exist_ok=True)
        self.items_dir.mkdir(parents=True, exist_ok=True)
        self._salt = secrets.token_bytes(SALT_SIZE)
        params = {
            "kdf": KDF_ID_PBKDF2,
            "iterations": self._iterations,
            "salt": self._salt.hex(),
            "created": time.time(),
        }
        atomic_write_bytes(self._dat, HEADER + json.dumps(params).encode("utf-8"))
        # Write an empty encrypted index to validate the password immediately.
        self._key = bytearray(derive_key(password, self._salt, self._iterations))
        self.locked = False
        self._write_index({})
        # Leave the vault unlocked: the user just provided the password.

    def unlock(self, password: str) -> None:
        if not self.exists():
            raise VaultError("No vault exists")
        raw = self._dat.read_bytes()
        if not raw.startswith(HEADER):
            raise VaultError("Vault header is damaged")
        try:
            params = json.loads(raw[len(HEADER):].decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise VaultError("Vault parameters are damaged")
        self._salt = bytes.fromhex(params["salt"])
        self._iterations = int(params.get("iterations", PBKDF2_ITERATIONS))
        key = derive_key(password, self._salt, self._iterations)
        # Validate by decrypting the index.
        try:
            self._read_index(bytes(key))
        except InvalidPasswordError:
            _zeroize(bytearray(key))
            raise
        except VaultError as e:
            _zeroize(bytearray(key))
            raise VaultError(f"Vault is damaged: {e}")
        self._key = bytearray(key)
        self.locked = False

    def lock(self) -> None:
        """Wipe key material from memory (best-effort)."""
        _zeroize(self._key)
        self._key = None
        self.locked = True

    def is_locked(self) -> bool:
        return self.locked

    def _require_unlocked(self) -> bytes:
        if self._key is None:
            raise VaultLockedError("The vault is locked")
        return bytes(self._key)

    # -- index (encrypted) ---------------------------------------------------
    def _read_index(self, key: bytes) -> dict:
        if not self._index.exists():
            return {}
        blob = self._index.read_bytes()
        nonce, ciphertext = blob[:NONCE_SIZE], blob[NONCE_SIZE:]
        try:
            plain = AESGCM(key).decrypt(nonce, ciphertext, b"or-index")
        except Exception:
            raise InvalidPasswordError("Wrong password or damaged vault")
        return json.loads(plain.decode("utf-8"))

    def _write_index(self, index: dict) -> None:
        key = self._require_unlocked()
        nonce = secrets.token_bytes(NONCE_SIZE)
        ciphertext = AESGCM(key).encrypt(
            nonce, json.dumps(index).encode("utf-8"), b"or-index")
        atomic_write_bytes(self._index, nonce + ciphertext)

    # -- items ------------------------------------------------------------
    def add_item(self, name: str, source: Path, *, consume: bool = False) -> str:
        """Encrypt a file into the vault. Returns item id."""
        key = self._require_unlocked()
        index = self._read_index(key)
        item_id = secrets.token_hex(8)
        data = Path(source).read_bytes()
        nonce = secrets.token_bytes(NONCE_SIZE)
        ciphertext = AESGCM(key).encrypt(nonce, data, f"or-item:{item_id}".encode())
        item_path = self.items_dir / f"{item_id}.oritem"
        atomic_write_bytes(item_path, nonce + ciphertext)
        index[item_id] = {
            "name": name,
            "size": len(data),
            "added": time.time(),
        }
        self._write_index(index)
        if consume:
            secure_delete(Path(source))
        return item_id

    def extract_item(self, item_id: str, destination: Path) -> Path:
        """Decrypt an item to ``destination`` (validated by the caller)."""
        key = self._require_unlocked()
        index = self._read_index(key)
        if item_id not in index:
            raise VaultError("Unknown vault item")
        item_path = self.items_dir / f"{item_id}.oritem"
        if not item_path.exists():
            raise VaultError("Vault item file is missing")
        blob = item_path.read_bytes()
        nonce, ciphertext = blob[:NONCE_SIZE], blob[NONCE_SIZE:]
        try:
            plain = AESGCM(key).decrypt(nonce, ciphertext,
                                        f"or-item:{item_id}".encode())
        except Exception:
            raise VaultError("Vault item failed authentication — it is corrupted or tampered with")
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_bytes(destination, plain)
        return destination

    def list_items(self) -> list[dict]:
        key = self._require_unlocked()
        index = self._read_index(key)
        return [{"id": iid, **meta} for iid, meta in index.items()]

    def remove_item(self, item_id: str, *, secure: bool = True) -> None:
        key = self._require_unlocked()
        index = self._read_index(key)
        if item_id not in index:
            raise VaultError("Unknown vault item")
        del index[item_id]
        self._write_index(index)
        item_path = self.items_dir / f"{item_id}.oritem"
        if item_path.exists():
            if secure:
                secure_delete(item_path)
            else:
                item_path.unlink(missing_ok=True)

    def change_password(self, old_password: str, new_password: str) -> None:
        # Verify old password by decrypting the index.
        self.unlock(old_password)
        items = self.list_items()
        key_old = bytes(self._key)
        # Re-encrypt everything under a new salt+key.
        new_salt = secrets.token_bytes(SALT_SIZE)
        key_new = derive_key(new_password, new_salt, PBKDF2_ITERATIONS)
        reencrypted: dict = {}
        aes_new = AESGCM(key_new)
        for item in items:
            iid = item["id"]
            item_path = self.items_dir / f"{iid}.oritem"
            blob = item_path.read_bytes()
            nonce, ciphertext = blob[:NONCE_SIZE], blob[NONCE_SIZE:]
            plain = AESGCM(key_old).decrypt(
                nonce, ciphertext, f"or-item:{iid}".encode())
            new_nonce = secrets.token_bytes(NONCE_SIZE)
            new_ct = aes_new.encrypt(new_nonce, plain, f"or-item:{iid}".encode())
            atomic_write_bytes(item_path, new_nonce + new_ct)
            reencrypted[iid] = item
        _zeroize(self._key)
        self._key = bytearray(key_new)
        self._salt = new_salt
        params = {
            "kdf": KDF_ID_PBKDF2,
            "iterations": PBKDF2_ITERATIONS,
            "salt": new_salt.hex(),
            "created": time.time(),
        }
        atomic_write_bytes(self._dat, HEADER + json.dumps(params).encode("utf-8"))
        self._write_index(reencrypted)
        self.lock()


def vault_directory() -> Path:
    from omnireader_pro.app import paths
    return paths.vault_dir()
