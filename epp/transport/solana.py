"""
Solana transport for EPP - blockchain-based envelope delivery.

Envelopes are stored as transaction memos on Solana, addressed to the
recipient's public key. Recipients poll for new transactions to receive
envelopes without running a server.

Costs:
- Send: ~0.000005 SOL (~$0.0002 USD) per envelope
- Receive: Free (read-only RPC calls)

Requirements:
- pip install solana solders
"""

import base64
import json
from typing import AsyncIterator, Optional

from .base import Transport
from epp.models import Envelope

# Solana Memo Program ID
MEMO_PROGRAM_ID = "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr"

# EPP memo prefix for identification
EPP_MEMO_PREFIX = '{"epp":"1"'


class SolanaTransport(Transport):
    """
    Solana blockchain transport for EPP envelopes.

    Sender pays transaction fees (~$0.0002), recipient reads for free.
    Envelopes persist on-chain indefinitely.
    """

    def __init__(
        self,
        rpc_url: str = "https://api.mainnet-beta.solana.com",
        keypair_path: Optional[str] = None,
    ):
        """
        Initialize Solana transport.

        Args:
            rpc_url: Solana RPC endpoint URL
            keypair_path: Path to sender's Solana keypair JSON file
        """
        self.rpc_url = rpc_url
        self.keypair_path = keypair_path
        self._client = None
        self._keypair = None

    async def _get_client(self):
        """Lazy-load Solana client."""
        if self._client is None:
            try:
                from solana.rpc.async_api import AsyncClient

                self._client = AsyncClient(self.rpc_url)
            except ImportError:
                raise ImportError(
                    "Solana transport requires 'solana' package. "
                    "Install with: pip install solana solders"
                )
        return self._client

    async def _get_keypair(self):
        """Load sender keypair for signing transactions."""
        if self._keypair is None:
            if self.keypair_path is None:
                raise ValueError("keypair_path required for sending")
            try:
                from solders.keypair import Keypair

                with open(self.keypair_path, "r") as f:
                    secret = json.load(f)
                self._keypair = Keypair.from_bytes(bytes(secret))
            except ImportError:
                raise ImportError(
                    "Solana transport requires 'solders' package. "
                    "Install with: pip install solana solders"
                )
        return self._keypair

    def _envelope_to_memo(self, envelope: Envelope) -> str:
        """
        Convert EPP envelope to Solana memo format.

        Format: {"epp":"1","env":"<base64-encoded-envelope-json>"}

        For envelopes > 800 bytes, consider using Arweave storage
        and posting just the pointer.
        """
        envelope_json = envelope.model_dump_json()
        envelope_b64 = base64.b64encode(envelope_json.encode()).decode()

        memo = json.dumps(
            {
                "epp": "1",
                "env": envelope_b64,
            },
            separators=(",", ":"),
        )

        return memo

    def _memo_to_envelope(self, memo: str) -> Optional[Envelope]:
        """
        Parse Solana memo back to EPP envelope.

        Returns None if memo is not a valid EPP envelope.
        """
        if not memo.startswith(EPP_MEMO_PREFIX):
            return None

        try:
            data = json.loads(memo)
            if data.get("epp") != "1":
                return None

            # Direct envelope encoding
            if "env" in data:
                envelope_json = base64.b64decode(data["env"]).decode()
                return Envelope.model_validate_json(envelope_json)

            # Pointer to external storage (Arweave, IPFS)
            if "loc" in data:
                # TODO: Fetch from external storage
                raise NotImplementedError(f"External storage not yet implemented: {data['loc']}")

            return None
        except Exception:
            return None

    async def send(self, envelope: Envelope, recipient_address: str) -> str:
        """
        Send EPP envelope via Solana memo transaction.

        Args:
            envelope: The signed EPP envelope
            recipient_address: Solana address (base58) of recipient
                             (can be derived from EPP pubkey)

        Returns:
            Solana transaction signature
        """
        try:
            from solders.instruction import Instruction, AccountMeta
            from solders.pubkey import Pubkey
            from solders.message import Message
        except ImportError:
            raise ImportError(
                "Solana transport requires 'solana' and 'solders' packages. "
                "Install with: pip install solana solders"
            )

        client = await self._get_client()
        keypair = await self._get_keypair()

        memo = self._envelope_to_memo(envelope)
        memo_program = Pubkey.from_string(MEMO_PROGRAM_ID)

        # Create memo instruction
        # Include recipient as a non-signer account for indexing
        recipient_pubkey = Pubkey.from_string(recipient_address)

        instruction = Instruction(
            program_id=memo_program,
            accounts=[
                AccountMeta(pubkey=keypair.pubkey(), is_signer=True, is_writable=False),
                AccountMeta(pubkey=recipient_pubkey, is_signer=False, is_writable=False),
            ],
            data=memo.encode("utf-8"),
        )

        # Build and send transaction
        recent_blockhash = await client.get_latest_blockhash()
        message = Message.new_with_blockhash(
            [instruction],
            keypair.pubkey(),
            recent_blockhash.value.blockhash,
        )

        from solders.transaction import Transaction as SoldersTransaction

        tx = SoldersTransaction.new_unsigned(message)
        tx.sign([keypair], recent_blockhash.value.blockhash)

        result = await client.send_transaction(tx)
        return str(result.value)

    async def receive(
        self,
        recipient_pubkey: str,
        since: Optional[str] = None,
        limit: int = 100,
    ) -> AsyncIterator[Envelope]:
        """
        Fetch EPP envelopes from Solana addressed to recipient.

        Args:
            recipient_pubkey: EPP public key (64-char hex) or Solana address
            since: Transaction signature to start after (for pagination)
            limit: Maximum transactions to fetch per call

        Yields:
            EPP envelopes addressed to the recipient
        """
        try:
            from solders.pubkey import Pubkey
            from solders.signature import Signature
        except ImportError:
            raise ImportError(
                "Solana transport requires 'solders' package. "
                "Install with: pip install solana solders"
            )

        client = await self._get_client()

        # Convert EPP pubkey to Solana address if needed
        if len(recipient_pubkey) == 64:
            # It's an EPP hex pubkey - derive Solana address
            solana_address = self._epp_pubkey_to_solana(recipient_pubkey)
        else:
            solana_address = Pubkey.from_string(recipient_pubkey)

        # Fetch transaction signatures
        before_sig = Signature.from_string(since) if since else None
        response = await client.get_signatures_for_address(
            solana_address,
            before=before_sig,
            limit=limit,
        )

        for sig_info in response.value:
            if sig_info.memo is None:
                continue

            envelope = self._memo_to_envelope(sig_info.memo)
            if envelope is not None:
                yield envelope

    def _epp_pubkey_to_solana(self, epp_pubkey_hex: str):
        """
        Derive a Solana address from an EPP Ed25519 public key.

        Both use Ed25519, so the raw bytes are compatible.
        """
        from solders.pubkey import Pubkey

        pubkey_bytes = bytes.fromhex(epp_pubkey_hex)
        return Pubkey(pubkey_bytes)

    async def close(self):
        """Close the RPC connection."""
        if self._client:
            await self._client.close()
            self._client = None


def epp_pubkey_to_solana_address(epp_pubkey_hex: str) -> str:
    """
    Convert an EPP public key (64-char hex) to a Solana address (base58).

    EPP uses Ed25519, same as Solana, so the conversion is direct.

    Args:
        epp_pubkey_hex: 64-character hex string of Ed25519 public key

    Returns:
        Base58-encoded Solana address
    """
    from solders.pubkey import Pubkey

    pubkey_bytes = bytes.fromhex(epp_pubkey_hex)
    return str(Pubkey(pubkey_bytes))
