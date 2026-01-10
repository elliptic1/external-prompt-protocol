"""
Cryptographic key management for EPP.
"""

import os
from typing import Tuple
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives import serialization


class KeyPair:
    """Represents an Ed25519 key pair for EPP."""

    def __init__(self, private_key: Ed25519PrivateKey):
        self.private_key = private_key
        self.public_key = private_key.public_key()

    @classmethod
    def generate(cls) -> "KeyPair":
        """Generate a new Ed25519 key pair."""
        private_key = Ed25519PrivateKey.generate()
        return cls(private_key)

    @classmethod
    def from_private_bytes(cls, private_bytes: bytes) -> "KeyPair":
        """Load a key pair from raw private key bytes."""
        private_key = Ed25519PrivateKey.from_private_bytes(private_bytes)
        return cls(private_key)

    @classmethod
    def from_private_pem(cls, pem_data: bytes, password: bytes | None = None) -> "KeyPair":
        """Load a key pair from PEM-encoded private key."""
        private_key = serialization.load_pem_private_key(pem_data, password=password)
        if not isinstance(private_key, Ed25519PrivateKey):
            raise ValueError("Key is not an Ed25519 private key")
        return cls(private_key)

    def private_key_bytes(self) -> bytes:
        """Export private key as raw bytes."""
        return self.private_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        )

    def private_key_pem(self, password: bytes | None = None) -> bytes:
        """Export private key as PEM."""
        encryption = (
            serialization.BestAvailableEncryption(password)
            if password
            else serialization.NoEncryption()
        )
        return self.private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=encryption,
        )

    def public_key_bytes(self) -> bytes:
        """Export public key as raw bytes."""
        return self.public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )

    def public_key_hex(self) -> str:
        """Export public key as hexadecimal string."""
        return self.public_key_bytes().hex()

    def save_to_files(
        self,
        private_path: str,
        public_path: str,
        password: bytes | None = None,
    ) -> None:
        """Save key pair to separate files."""
        # Save private key (PEM format, optionally encrypted)
        with open(private_path, "wb") as f:
            f.write(self.private_key_pem(password))
        os.chmod(private_path, 0o600)  # Restrict permissions

        # Save public key (hex format)
        with open(public_path, "w") as f:
            f.write(self.public_key_hex())

    @classmethod
    def load_from_file(cls, private_path: str, password: bytes | None = None) -> "KeyPair":
        """Load key pair from private key file."""
        with open(private_path, "rb") as f:
            pem_data = f.read()
        return cls.from_private_pem(pem_data, password)


class PublicKey:
    """Represents an Ed25519 public key for verifying signatures."""

    def __init__(self, public_key: Ed25519PublicKey):
        self.public_key = public_key

    @classmethod
    def from_bytes(cls, public_bytes: bytes) -> "PublicKey":
        """Load public key from raw bytes."""
        public_key = Ed25519PublicKey.from_public_bytes(public_bytes)
        return cls(public_key)

    @classmethod
    def from_hex(cls, hex_string: str) -> "PublicKey":
        """Load public key from hexadecimal string."""
        public_bytes = bytes.fromhex(hex_string)
        return cls.from_bytes(public_bytes)

    @classmethod
    def from_file(cls, public_path: str) -> "PublicKey":
        """Load public key from file (hex format)."""
        with open(public_path, "r") as f:
            hex_string = f.read().strip()
        return cls.from_hex(hex_string)

    def to_bytes(self) -> bytes:
        """Export public key as raw bytes."""
        return self.public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )

    def to_hex(self) -> str:
        """Export public key as hexadecimal string."""
        return self.to_bytes().hex()

    def __eq__(self, other: object) -> bool:
        """Check equality based on public key bytes."""
        if not isinstance(other, PublicKey):
            return False
        return self.to_bytes() == other.to_bytes()

    def __hash__(self) -> int:
        """Hash based on public key bytes."""
        return hash(self.to_bytes())
