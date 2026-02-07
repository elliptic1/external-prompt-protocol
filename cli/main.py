"""
EPP CLI tool (eppctl) for key management and envelope operations.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

import click
import httpx

from epp.crypto.keys import KeyPair, PublicKey
from epp.crypto.signing import generate_nonce, sign_envelope
from epp.models import Envelope, Payload
from epp.policy.trust_registry import RateLimit, SenderPolicy, TrustRegistry


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
def add(
    registry: str,
    public_key: str,
    name: str,
    scopes: str,
    max_size: int,
    max_per_hour: Optional[int],
    max_per_day: Optional[int],
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


if __name__ == "__main__":
    cli()
