"""
EPP CLI tool (eppctl) for key management and envelope operations.
"""

import base64
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Tuple
from uuid import uuid4

import click
import httpx

from epp.attestations import (
    Attestations,
    create_attestation_entry,
    verify_attestations,
)
from epp.capabilities import Capabilities, FilesystemCapabilities, NetworkCapabilities
from epp.chain_identity import ChainIdentity
from epp.crypto.integrity import compute_payload_hash
from epp.crypto.keys import KeyPair, PublicKey
from epp.crypto.signing import generate_nonce, sign_envelope
from epp.models import Envelope, Payload
from epp.payment import PaymentRequest
from epp.policy.trust_registry import RateLimit, SenderPolicy, TrustRegistry
from epp.provenance import (
    Provenance,
    add_attestation,
    create_provenance_entry,
    verify_provenance_chain,
)
from epp.revocation import RevocationCheck


@click.group()
@click.version_option(version="1.0.0")
def cli() -> None:
    """EPP CLI - External Prompt Protocol command-line tool."""
    pass


# Key management commands
@cli.group()
def keys() -> None:
    """Key management commands."""
    pass


@keys.command()
@click.option(
    "--output",
    "-o",
    default="sender",
    help="Output file prefix (generates <prefix>.key and <prefix>.pub)",
)
@click.option(
    "--password",
    "-p",
    is_flag=True,
    help="Encrypt private key with password",
)
def generate(output: str, password: bool) -> None:
    """Generate a new Ed25519 key pair."""
    key_pair = KeyPair.generate()

    private_path = f"{output}.key"
    public_path = f"{output}.pub"

    pwd = None
    if password:
        pwd = click.prompt("Enter password", hide_input=True, confirmation_prompt=True).encode()

    key_pair.save_to_files(private_path, public_path, password=pwd)

    click.echo("✓ Generated new key pair")
    click.echo(f"  Private key: {private_path}")
    click.echo(f"  Public key:  {public_path}")
    click.echo(f"\nPublic key (hex): {key_pair.public_key_hex()}")


@keys.command()
@click.argument("public_key_file", type=click.Path(exists=True))
def show(public_key_file: str) -> None:
    """Show public key information."""
    public_key = PublicKey.from_file(public_key_file)
    click.echo(f"Public key (hex): {public_key.to_hex()}")
    click.echo(f"Public key (bytes): {len(public_key.to_bytes())} bytes")


# Trust registry commands
@cli.group()
def trust() -> None:
    """Trust registry management."""
    pass


@trust.command()
@click.option(
    "--registry",
    "-r",
    default=".epp-inbox/data/trust_registry.json",
    help="Path to trust registry file",
)
@click.option("--public-key", "-k", required=True, help="Sender's public key (hex)")
@click.option("--name", "-n", required=True, help="Human-readable name for sender")
@click.option(
    "--scopes",
    "-s",
    default="*",
    help="Allowed scopes (comma-separated, or * for all)",
)
@click.option(
    "--max-size",
    default=10 * 1024 * 1024,
    help="Maximum envelope size in bytes",
)
@click.option("--max-per-hour", type=int, help="Maximum envelopes per hour")
@click.option("--max-per-day", type=int, help="Maximum envelopes per day")
@click.option(
    "--revocation-check-url",
    help="If set, inbox MUST consult this URL for sender revocation status (v1.1)",
)
@click.option(
    "--revocation-on-failure",
    type=click.Choice(["deny", "allow", "log-only"]),
    default="deny",
    help="What to do when revocation lookup fails or returns revoked (v1.1)",
)
def add(
    registry: str,
    public_key: str,
    name: str,
    scopes: str,
    max_size: int,
    max_per_hour: Optional[int],
    max_per_day: Optional[int],
    revocation_check_url: Optional[str],
    revocation_on_failure: str,
) -> None:
    """Add a trusted sender to the registry."""
    trust_registry = TrustRegistry(storage_path=registry)

    # Parse scopes
    scope_list = [s.strip() for s in scopes.split(",")]

    # Create policy
    policy = SenderPolicy(
        allowed_scopes=scope_list,
        max_envelope_size=max_size,
        rate_limit=RateLimit(max_per_hour=max_per_hour, max_per_day=max_per_day),
        revocation_check_url=revocation_check_url,
        revocation_on_failure=revocation_on_failure,
    )

    try:
        entry = trust_registry.add_sender(public_key, name, policy)
        click.echo(f"✓ Added trusted sender: {name}")
        click.echo(f"  Public key: {entry.public_key}")
        click.echo(f"  Allowed scopes: {', '.join(entry.policy.allowed_scopes)}")
        click.echo(f"  Max size: {entry.policy.max_envelope_size} bytes")
        if entry.policy.rate_limit.max_per_hour:
            click.echo(f"  Max per hour: {entry.policy.rate_limit.max_per_hour}")
        if entry.policy.rate_limit.max_per_day:
            click.echo(f"  Max per day: {entry.policy.rate_limit.max_per_day}")
    except ValueError as e:
        click.echo(f"✗ Error: {e}", err=True)
        raise click.Abort()


@trust.command()
@click.option(
    "--registry",
    "-r",
    default=".epp-inbox/data/trust_registry.json",
    help="Path to trust registry file",
)
@click.option("--public-key", "-k", required=True, help="Sender's public key (hex)")
def remove(registry: str, public_key: str) -> None:
    """Remove a sender from the trust registry."""
    trust_registry = TrustRegistry(storage_path=registry)

    try:
        trust_registry.remove_sender(public_key)
        click.echo(f"✓ Removed sender: {public_key[:16]}...")
    except ValueError as e:
        click.echo(f"✗ Error: {e}", err=True)
        raise click.Abort()


@trust.command(name="list")
@click.option(
    "--registry",
    "-r",
    default=".epp-inbox/data/trust_registry.json",
    help="Path to trust registry file",
)
def list_senders(registry: str) -> None:
    """List all trusted senders."""
    if not Path(registry).exists():
        click.echo("No trust registry found.")
        return

    trust_registry = TrustRegistry(storage_path=registry)
    senders = trust_registry.list_senders()

    if not senders:
        click.echo("No trusted senders.")
        return

    click.echo(f"Trusted senders ({len(senders)}):\n")
    for entry in senders:
        click.echo(f"  • {entry.name}")
        click.echo(f"    Public key: {entry.public_key}")
        click.echo(f"    Scopes: {', '.join(entry.policy.allowed_scopes)}")
        click.echo(f"    Added: {entry.added_at}")
        click.echo()


# Envelope commands
@cli.group()
def envelope() -> None:
    """Envelope creation and sending."""
    pass


@envelope.command()
@click.option("--private-key", "-k", required=True, type=click.Path(exists=True))
@click.option("--recipient", "-r", required=True, help="Recipient's public key (hex)")
@click.option("--scope", "-s", required=True, help="Scope identifier")
@click.option("--prompt", "-p", required=True, help="Prompt text")
@click.option("--context", "-c", help="Context JSON file", type=click.Path(exists=True))
@click.option("--expires", "-e", default=15, help="Expiration time in minutes (default: 15)")
@click.option("--output", "-o", help="Output file (default: print to stdout)")
@click.option("--password", help="Private key password")
@click.option("--conversation-id", help="Conversation thread ID (UUID)")
@click.option("--new-conversation", is_flag=True, help="Auto-generate a new conversation ID")
@click.option("--in-reply-to", help="Envelope ID being replied to (UUID)")
@click.option("--payload-type", help="Payload type hint (e.g., 'order-request')")
@click.option("--on-behalf-of", help="Public key hex for delegation (acting on behalf of)")
# v1.1 flags
@click.option("--hash", "add_hash", is_flag=True, help="Compute SHA-256 integrity hash of payload")
@click.option("--hash-alg", default="sha256", type=click.Choice(["sha256", "sha384", "sha512"]))
@click.option("--payment-required", is_flag=True, help="Mark payment as required")
@click.option("--payment-amount", help="Payment amount (e.g., '0.01')")
@click.option("--payment-currency", help="Payment currency (USDC, ETH, ...)")
@click.option("--payment-recipient", help="Payment wallet address")
@click.option("--payment-chain", help="Payment chain (base, ethereum, ...)")
@click.option("--payment-memo", help="Optional payment memo")
@click.option("--payment-expires-in", type=int, help="Payment deadline in minutes from now")
@click.option("--capability-fs-read", multiple=True, help="Filesystem read path (repeatable)")
@click.option("--capability-fs-write", multiple=True, help="Filesystem write path (repeatable)")
@click.option("--capability-net-domain", multiple=True, help="Network domain (repeatable)")
@click.option("--capability-action", multiple=True, help="Action capability (repeatable)")
@click.option("--capability-data-access", multiple=True, help="Data access capability (repeatable)")
@click.option("--chain-identity-standard", help="Identity standard (erc-8004, ens, lens, did)")
@click.option("--chain-identity-chain", help="Chain (base, ethereum, ...)")
@click.option("--chain-identity-contract", help="Contract address")
@click.option("--chain-identity-token-id", help="NFT token ID")
@click.option("--chain-identity-identifier", help="Off-chain identifier (e.g. 'alice.eth')")
@click.option(
    "--chain-identity-verification",
    type=click.Choice(["on-chain-lookup", "attestation", "oracle", "self"]),
    default="on-chain-lookup",
)
@click.option("--revocation-registry", help="Revocation registry URL or DID")
@click.option(
    "--revocation-required/--revocation-optional",
    default=True,
    help="Whether the revocation check is mandatory",
)
def create(
    private_key: str,
    recipient: str,
    scope: str,
    prompt: str,
    context: Optional[str],
    expires: int,
    output: Optional[str],
    password: Optional[str],
    conversation_id: Optional[str],
    new_conversation: bool,
    in_reply_to: Optional[str],
    payload_type: Optional[str],
    on_behalf_of: Optional[str],
    add_hash: bool,
    hash_alg: str,
    payment_required: bool,
    payment_amount: Optional[str],
    payment_currency: Optional[str],
    payment_recipient: Optional[str],
    payment_chain: Optional[str],
    payment_memo: Optional[str],
    payment_expires_in: Optional[int],
    capability_fs_read: Tuple[str, ...],
    capability_fs_write: Tuple[str, ...],
    capability_net_domain: Tuple[str, ...],
    capability_action: Tuple[str, ...],
    capability_data_access: Tuple[str, ...],
    chain_identity_standard: Optional[str],
    chain_identity_chain: Optional[str],
    chain_identity_contract: Optional[str],
    chain_identity_token_id: Optional[str],
    chain_identity_identifier: Optional[str],
    chain_identity_verification: str,
    revocation_registry: Optional[str],
    revocation_required: bool,
) -> None:
    """Create a signed EPP envelope."""
    # Load sender key
    pwd = password.encode() if password else None
    key_pair = KeyPair.load_from_file(private_key, password=pwd)

    # Load context if provided
    context_data = None
    if context:
        with open(context, "r") as f:
            context_data = json.load(f)

    # Handle conversation ID
    if new_conversation and conversation_id:
        click.echo("✗ Cannot use both --conversation-id and --new-conversation", err=True)
        raise click.Abort()
    if new_conversation:
        conversation_id = str(uuid4())

    # Create envelope
    envelope_id = str(uuid4())
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    expires_at = (
        (datetime.now(timezone.utc) + timedelta(minutes=expires)).isoformat().replace("+00:00", "Z")
    )
    nonce = generate_nonce()
    sender_hex = key_pair.public_key_hex()

    payload = Payload(prompt=prompt, context=context_data, payload_type=payload_type)

    # Build delegation if requested
    delegation_dict = None
    if on_behalf_of:
        delegation_dict = {"on_behalf_of": on_behalf_of}

    # Sign envelope
    signature = sign_envelope(
        key_pair,
        version="1",
        envelope_id=envelope_id,
        sender=sender_hex,
        recipient=recipient,
        timestamp=timestamp,
        expires_at=expires_at,
        nonce=nonce,
        scope=scope,
        payload=payload.model_dump(exclude_none=True),
        conversation_id=conversation_id,
        in_reply_to=in_reply_to,
        delegation=delegation_dict,
    )

    # Create envelope object
    envelope_dict: dict = {
        "version": "1",
        "envelope_id": envelope_id,
        "sender": sender_hex,
        "recipient": recipient,
        "timestamp": timestamp,
        "expires_at": expires_at,
        "nonce": nonce,
        "scope": scope,
        "payload": payload.model_dump(exclude_none=True),
        "signature": signature,
    }

    # Add optional fields
    if conversation_id:
        envelope_dict["conversation_id"] = conversation_id
    if in_reply_to:
        envelope_dict["in_reply_to"] = in_reply_to
    if delegation_dict:
        envelope_dict["delegation"] = delegation_dict

    # v1.1 fields
    if add_hash:
        from epp.crypto.integrity import Integrity

        digest = compute_payload_hash(payload.model_dump(exclude_none=True), hash_alg)
        envelope_dict["integrity"] = Integrity(alg=hash_alg, hash=digest).model_dump(
            exclude_none=True
        )

    if payment_amount or payment_required:
        if not (payment_amount and payment_currency and payment_recipient and payment_chain):
            raise click.UsageError(
                "Payment requires --payment-amount, --payment-currency, "
                "--payment-recipient, and --payment-chain"
            )
        payment_expires_at = None
        if payment_expires_in:
            payment_expires_at = (
                (datetime.now(timezone.utc) + timedelta(minutes=payment_expires_in))
                .isoformat()
                .replace("+00:00", "Z")
            )
        envelope_dict["payment"] = PaymentRequest(
            required=payment_required,
            amount=payment_amount,
            currency=payment_currency,
            recipient=payment_recipient,
            chain=payment_chain,
            memo=payment_memo,
            expires_at=payment_expires_at,
        ).model_dump(exclude_none=True)

    if (
        capability_fs_read
        or capability_fs_write
        or capability_net_domain
        or capability_action
        or capability_data_access
    ):
        fs = (
            FilesystemCapabilities(read=list(capability_fs_read), write=list(capability_fs_write))
            if (capability_fs_read or capability_fs_write)
            else None
        )
        net = (
            NetworkCapabilities(domains=list(capability_net_domain), protocols=[], ports=[])
            if capability_net_domain
            else None
        )
        envelope_dict["capabilities"] = Capabilities(
            filesystem=fs,
            network=net,
            actions=list(capability_action),
            data_access=list(capability_data_access),
        ).model_dump(exclude_none=True)

    if chain_identity_standard or chain_identity_chain:
        if not (chain_identity_standard and chain_identity_chain):
            raise click.UsageError(
                "ChainIdentity requires both --chain-identity-standard and --chain-identity-chain"
            )
        envelope_dict["chain_identity"] = ChainIdentity(
            standard=chain_identity_standard,
            chain=chain_identity_chain,
            contract=chain_identity_contract,
            token_id=chain_identity_token_id,
            identifier=chain_identity_identifier,
            verification_method=chain_identity_verification,
        ).model_dump(exclude_none=True)

    if revocation_registry:
        envelope_dict["revocation_check"] = RevocationCheck(
            registry=revocation_registry, required=revocation_required
        ).model_dump(exclude_none=True)

    # Validate envelope
    Envelope(**envelope_dict)

    # Output
    envelope_json = json.dumps(envelope_dict, indent=2)

    if output:
        with open(output, "w") as f:
            f.write(envelope_json)
        click.echo(f"✓ Created envelope: {envelope_id}")
        click.echo(f"  Saved to: {output}")
        if conversation_id:
            click.echo(f"  Conversation: {conversation_id}")
        if in_reply_to:
            click.echo(f"  In reply to: {in_reply_to}")
        if on_behalf_of:
            click.echo(f"  On behalf of: {on_behalf_of[:16]}...")
    else:
        click.echo(envelope_json)


@envelope.command()
@click.argument("envelope_file", type=click.Path(exists=True))
@click.argument("inbox_url")
@click.option("--timeout", default=30, help="Request timeout in seconds")
def send(envelope_file: str, inbox_url: str, timeout: int) -> None:
    """Send an envelope to an inbox."""
    # Load envelope
    with open(envelope_file, "r") as f:
        envelope_data = json.load(f)

    envelope = Envelope(**envelope_data)

    # Ensure URL has proper endpoint
    if not inbox_url.endswith("/epp/v1/submit"):
        inbox_url = inbox_url.rstrip("/") + "/epp/v1/submit"

    click.echo(f"Sending envelope {envelope.envelope_id} to {inbox_url}...")

    try:
        response = httpx.post(
            inbox_url,
            json=envelope_data,
            timeout=timeout,
            headers={"Content-Type": "application/json"},
        )

        receipt = response.json()

        if response.status_code == 200:
            click.echo("✓ Envelope accepted")
            click.echo(f"  Receipt ID: {receipt.get('receipt_id')}")
            click.echo(f"  Executor: {receipt.get('executor')}")
        else:
            click.echo(f"✗ Envelope rejected ({response.status_code})", err=True)
            if "error" in receipt:
                click.echo(f"  Error: {receipt['error']['code']}", err=True)
                click.echo(f"  Message: {receipt['error']['message']}", err=True)

    except httpx.RequestError as e:
        click.echo(f"✗ Request failed: {e}", err=True)
        raise click.Abort()
    except Exception as e:
        click.echo(f"✗ Error: {e}", err=True)
        raise click.Abort()


def _load_envelope(path: str) -> dict:
    with open(path, "r") as f:
        return json.load(f)


def _save_envelope(path: str, envelope_dict: dict) -> None:
    Envelope(**envelope_dict)  # validate
    with open(path, "w") as f:
        json.dump(envelope_dict, f, indent=2)


def _make_sign_func(key_pair: KeyPair):
    def sign(data: bytes) -> str:
        return base64.b64encode(key_pair.private_key.sign(data)).decode("ascii")

    return sign


def _make_verify_func():
    from cryptography.exceptions import InvalidSignature

    def verify(identity_hex: str, payload: bytes, sig_b64: str) -> bool:
        try:
            PublicKey.from_hex(identity_hex).public_key.verify(base64.b64decode(sig_b64), payload)
            return True
        except (InvalidSignature, Exception):
            return False

    return verify


def _envelope_subject_hash(envelope_dict: dict, alg: str = "sha256") -> str:
    """Subject hash for attestation = hash of payload (matches integrity default)."""
    return compute_payload_hash(envelope_dict["payload"], alg)


# Provenance commands
@cli.group()
def provenance() -> None:
    """Provenance chain operations (v1.1)."""
    pass


@provenance.command("add")
@click.option("--envelope", "-e", required=True, type=click.Path(exists=True))
@click.option("--private-key", "-k", required=True, type=click.Path(exists=True))
@click.option("--password", help="Private key password")
@click.option(
    "--role",
    "-r",
    required=True,
    help="Attestor role (author, auditor, reviewer, voucher, forwarder, ...)",
)
@click.option("--statement", "-s", help="Optional human-readable statement")
def provenance_add(
    envelope: str,
    private_key: str,
    password: Optional[str],
    role: str,
    statement: Optional[str],
) -> None:
    """Add a provenance attestation to an existing envelope JSON file."""
    pwd = password.encode() if password else None
    key_pair = KeyPair.load_from_file(private_key, password=pwd)

    envelope_dict = _load_envelope(envelope)
    content_hash = _envelope_subject_hash(envelope_dict)

    if "provenance" in envelope_dict and envelope_dict["provenance"]:
        existing = Provenance(**envelope_dict["provenance"])
        if existing.content_hash != content_hash:
            raise click.UsageError(
                "Existing provenance.content_hash does not match envelope payload hash"
            )
        new_chain = add_attestation(
            provenance=existing,
            role=role,
            identity=key_pair.public_key_hex(),
            sign_func=_make_sign_func(key_pair),
            statement=statement,
        )
    else:
        first = create_provenance_entry(
            role=role,
            identity=key_pair.public_key_hex(),
            content_hash=content_hash,
            sign_func=_make_sign_func(key_pair),
            statement=statement,
        )
        new_chain = Provenance(content_hash=content_hash, entries=[first])

    envelope_dict["provenance"] = new_chain.model_dump(exclude_none=True)
    _save_envelope(envelope, envelope_dict)
    click.echo(
        f"✓ Added provenance entry: role={role}, identity={key_pair.public_key_hex()[:16]}..."
    )
    click.echo(f"  Chain depth: {new_chain.chain_depth()}")


@provenance.command("verify")
@click.option("--envelope", "-e", required=True, type=click.Path(exists=True))
def provenance_verify(envelope: str) -> None:
    """Verify the provenance chain on an envelope JSON file."""
    envelope_dict = _load_envelope(envelope)
    if not envelope_dict.get("provenance"):
        click.echo("No provenance chain present.")
        return
    chain = Provenance(**envelope_dict["provenance"])
    expected = _envelope_subject_hash(envelope_dict)
    if chain.content_hash != expected:
        click.echo(f"✗ content_hash mismatch: {chain.content_hash} != {expected}", err=True)
        raise click.Abort()
    ok, errors = verify_provenance_chain(chain, _make_verify_func())
    if ok:
        click.echo(f"✓ Provenance chain valid ({chain.chain_depth()} entries)")
        for entry in chain.entries:
            click.echo(f"  - {entry.role}: {entry.identity[:16]}... @ {entry.timestamp}")
    else:
        click.echo("✗ Provenance chain invalid:", err=True)
        for err in errors:
            click.echo(f"  - {err}", err=True)
        raise click.Abort()


# Attestation commands
@cli.group()
def attestation() -> None:
    """Multi-party attestation operations (v1.1)."""
    pass


@attestation.command("add")
@click.option("--envelope", "-e", required=True, type=click.Path(exists=True))
@click.option("--private-key", "-k", required=True, type=click.Path(exists=True))
@click.option("--password", help="Private key password")
@click.option("--role", "-r", required=True, help="Attestor role")
@click.option("--statement", "-s", help="Optional statement")
@click.option("--threshold", "-t", type=int, default=1, help="Threshold (used when initializing)")
@click.option(
    "--required-role",
    multiple=True,
    help="Role required by the attestation set (used when initializing, repeatable)",
)
def attestation_add(
    envelope: str,
    private_key: str,
    password: Optional[str],
    role: str,
    statement: Optional[str],
    threshold: int,
    required_role: Tuple[str, ...],
) -> None:
    """Add an attestation entry to an envelope's attestations set."""
    pwd = password.encode() if password else None
    key_pair = KeyPair.load_from_file(private_key, password=pwd)

    envelope_dict = _load_envelope(envelope)
    subject_hash = _envelope_subject_hash(envelope_dict)

    new_entry = create_attestation_entry(
        role=role,
        identity=key_pair.public_key_hex(),
        subject_hash=subject_hash,
        sign_func=_make_sign_func(key_pair),
        statement=statement,
    )

    if envelope_dict.get("attestations"):
        existing = envelope_dict["attestations"]
        existing["entries"].append(new_entry.model_dump(exclude_none=True))
        attestations_obj = Attestations(**existing)
    else:
        attestations_obj = Attestations(
            threshold=threshold,
            required_roles=list(required_role),
            entries=[new_entry],
        )

    envelope_dict["attestations"] = attestations_obj.model_dump(exclude_none=True)
    _save_envelope(envelope, envelope_dict)
    click.echo(f"✓ Added attestation: role={role}, identity={key_pair.public_key_hex()[:16]}...")
    click.echo(
        f"  Threshold: {attestations_obj.threshold}, " f"entries: {len(attestations_obj.entries)}"
    )


@attestation.command("verify")
@click.option("--envelope", "-e", required=True, type=click.Path(exists=True))
def attestation_verify(envelope: str) -> None:
    """Verify the attestations on an envelope JSON file."""
    envelope_dict = _load_envelope(envelope)
    if not envelope_dict.get("attestations"):
        click.echo("No attestations present.")
        return
    attestations_obj = Attestations(**envelope_dict["attestations"])
    subject_hash = _envelope_subject_hash(envelope_dict)
    ok, errors = verify_attestations(attestations_obj, subject_hash, _make_verify_func())
    if ok:
        click.echo(
            f"✓ Attestations valid (threshold={attestations_obj.threshold}, "
            f"entries={len(attestations_obj.entries)})"
        )
        for entry in attestations_obj.entries:
            click.echo(f"  - {entry.role}: {entry.identity[:16]}... @ {entry.timestamp}")
    else:
        click.echo("✗ Attestations invalid:", err=True)
        for err in errors:
            click.echo(f"  - {err}", err=True)
        raise click.Abort()


if __name__ == "__main__":
    cli()
