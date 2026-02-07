"""EPP Transport Layer - Pluggable delivery mechanisms."""

from .base import Transport
from .http import HttpTransport

__all__ = ["Transport", "HttpTransport"]

# Optional Solana transport (requires: pip install solana solders)
try:
    from .solana import SolanaTransport, epp_pubkey_to_solana_address  # noqa: F401

    __all__.extend(["SolanaTransport", "epp_pubkey_to_solana_address"])
except ImportError:
    pass
