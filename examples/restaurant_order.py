#!/usr/bin/env python3
"""
Restaurant Order EPP example: Multi-step commerce conversation.

This example demonstrates:
1. Mutual trust setup between customer and restaurant
2. 4-step conversation: menu query → menu response → order → confirmation
3. Conversation threading with in_reply_to chaining
4. Typed payloads (payload_type) for semantic routing
"""

import json
from datetime import datetime, timedelta
from uuid import uuid4

from epp.crypto.keys import KeyPair
from epp.crypto.signing import generate_nonce, sign_envelope
from epp.models import Envelope, Payload
from epp.policy.trust_registry import RateLimit, SenderPolicy, TrustRegistry


def create_signed_envelope(
    sender_key: KeyPair,
    recipient_hex: str,
    scope: str,
    prompt: str,
    context: dict = None,
    payload_type: str = None,
    conversation_id: str = None,
    in_reply_to: str = None,
) -> dict:
    """Helper to create a signed envelope dict."""
    envelope_id = str(uuid4())
    timestamp = datetime.utcnow().isoformat() + "Z"
    expires_at = (datetime.utcnow() + timedelta(minutes=15)).isoformat() + "Z"
    nonce = generate_nonce()
    sender_hex = sender_key.public_key_hex()

    payload = Payload(prompt=prompt, context=context, payload_type=payload_type)

    signature = sign_envelope(
        sender_key,
        version="1",
        envelope_id=envelope_id,
        sender=sender_hex,
        recipient=recipient_hex,
        timestamp=timestamp,
        expires_at=expires_at,
        nonce=nonce,
        scope=scope,
        payload=payload.model_dump(exclude_none=True),
        conversation_id=conversation_id,
        in_reply_to=in_reply_to,
    )

    envelope_dict: dict = {
        "version": "1",
        "envelope_id": envelope_id,
        "sender": sender_hex,
        "recipient": recipient_hex,
        "timestamp": timestamp,
        "expires_at": expires_at,
        "nonce": nonce,
        "scope": scope,
        "payload": payload.model_dump(exclude_none=True),
        "signature": signature,
    }

    if conversation_id:
        envelope_dict["conversation_id"] = conversation_id
    if in_reply_to:
        envelope_dict["in_reply_to"] = in_reply_to

    # Validate
    Envelope(**envelope_dict)
    return envelope_dict


def main() -> None:
    print("EPP Restaurant Order Example")
    print("=" * 60)

    # Step 1: Generate keys
    print("\n1. Generating keys...")
    customer_key = KeyPair.generate()
    restaurant_key = KeyPair.generate()

    print(f"   Customer:   {customer_key.public_key_hex()[:24]}...")
    print(f"   Restaurant: {restaurant_key.public_key_hex()[:24]}...")

    # Step 2: Mutual trust setup
    print("\n2. Setting up mutual trust...")

    # Customer trusts restaurant for commerce scopes
    customer_trust = TrustRegistry()
    customer_trust.add_sender(
        restaurant_key.public_key_hex(),
        "Luigi's Pizza",
        SenderPolicy(
            allowed_scopes=["menu", "order-confirmation", "commerce"],
            rate_limit=RateLimit(max_per_hour=20),
        ),
    )
    print("   Customer trusts: Luigi's Pizza (menu, order-confirmation, commerce)")

    # Restaurant trusts customer for ordering scopes
    restaurant_trust = TrustRegistry()
    restaurant_trust.add_sender(
        customer_key.public_key_hex(),
        "Customer Alice",
        SenderPolicy(
            allowed_scopes=["menu-query", "order-request", "commerce"],
            rate_limit=RateLimit(max_per_hour=10),
        ),
    )
    print("   Restaurant trusts: Customer Alice (menu-query, order-request, commerce)")

    # Step 3: Start conversation - Customer queries menu
    print("\n3. Customer queries menu...")
    conversation_id = str(uuid4())

    env1 = create_signed_envelope(
        sender_key=customer_key,
        recipient_hex=restaurant_key.public_key_hex(),
        scope="menu-query",
        prompt="What's on the menu tonight? I'm looking for pizza options and any specials.",
        payload_type="menu-query",
        conversation_id=conversation_id,
    )

    print(f"   Envelope: {env1['envelope_id'][:16]}...")
    print(f"   Conversation: {conversation_id[:16]}...")
    print(f"   Type: menu-query")

    # Step 4: Restaurant responds with menu
    print("\n4. Restaurant responds with menu...")

    env2 = create_signed_envelope(
        sender_key=restaurant_key,
        recipient_hex=customer_key.public_key_hex(),
        scope="menu",
        prompt="Tonight's menu at Luigi's Pizza. We have several options for you.",
        context={
            "menu_items": [
                {
                    "name": "Margherita",
                    "price": 14.99,
                    "description": "Classic tomato and mozzarella",
                },
                {"name": "Pepperoni", "price": 16.99, "description": "Loaded with pepperoni"},
                {"name": "Quattro Formaggi", "price": 18.99, "description": "Four cheese blend"},
            ],
            "specials": [
                {
                    "name": "Truffle Pizza",
                    "price": 22.99,
                    "description": "Black truffle and fontina",
                },
            ],
            "delivery_estimate": "30-45 minutes",
        },
        payload_type="menu-response",
        conversation_id=conversation_id,
        in_reply_to=env1["envelope_id"],
    )

    print(f"   Envelope: {env2['envelope_id'][:16]}...")
    print(f"   In reply to: {env1['envelope_id'][:16]}...")
    print(f"   Type: menu-response")
    print(f"   Items: 3 pizzas + 1 special")

    # Step 5: Customer places order
    print("\n5. Customer places order...")

    env3 = create_signed_envelope(
        sender_key=customer_key,
        recipient_hex=restaurant_key.public_key_hex(),
        scope="order-request",
        prompt="I'd like to place an order for delivery please.",
        context={
            "items": [
                {"name": "Margherita", "quantity": 1},
                {"name": "Truffle Pizza", "quantity": 1},
            ],
            "delivery_address": "123 Main St, Apt 4B",
            "payment_method": "card_ending_4242",
            "special_instructions": "Extra napkins please",
        },
        payload_type="order-request",
        conversation_id=conversation_id,
        in_reply_to=env2["envelope_id"],
    )

    print(f"   Envelope: {env3['envelope_id'][:16]}...")
    print(f"   In reply to: {env2['envelope_id'][:16]}...")
    print(f"   Type: order-request")
    print(f"   Items: 1x Margherita, 1x Truffle Pizza")

    # Step 6: Restaurant confirms order
    print("\n6. Restaurant confirms order...")

    env4 = create_signed_envelope(
        sender_key=restaurant_key,
        recipient_hex=customer_key.public_key_hex(),
        scope="order-confirmation",
        prompt="Your order has been confirmed and is being prepared!",
        context={
            "order_id": "ORD-2026-0207-001",
            "items": [
                {"name": "Margherita", "quantity": 1, "price": 14.99},
                {"name": "Truffle Pizza", "quantity": 1, "price": 22.99},
            ],
            "subtotal": 37.98,
            "tax": 3.42,
            "delivery_fee": 4.99,
            "total": 46.39,
            "estimated_delivery": "7:15 PM",
            "status": "preparing",
        },
        payload_type="order-confirmation",
        conversation_id=conversation_id,
        in_reply_to=env3["envelope_id"],
    )

    print(f"   Envelope: {env4['envelope_id'][:16]}...")
    print(f"   In reply to: {env3['envelope_id'][:16]}...")
    print(f"   Type: order-confirmation")
    print(f"   Order ID: ORD-2026-0207-001")
    print(f"   Total: $46.39")

    # Display conversation flow
    print("\n" + "=" * 60)
    print("Conversation Flow:")
    print("-" * 60)

    steps = [
        ("Customer → Restaurant", "menu-query", env1),
        ("Restaurant → Customer", "menu-response", env2),
        ("Customer → Restaurant", "order-request", env3),
        ("Restaurant → Customer", "order-confirmation", env4),
    ]

    for i, (direction, ptype, env) in enumerate(steps, 1):
        reply = env.get("in_reply_to", "N/A")
        if reply != "N/A":
            reply = reply[:16] + "..."
        print(f"\n  {i}. {direction}")
        print(f"     Type: {ptype}")
        print(f"     ID: {env['envelope_id'][:24]}...")
        print(f"     Reply to: {reply}")

    print(f"\n  All linked by conversation: {conversation_id}")
    print("\n" + "=" * 60)
    print("Complete ordering flow executed successfully!")
    print("No website, no app — just AI-to-AI communication.")


if __name__ == "__main__":
    main()
