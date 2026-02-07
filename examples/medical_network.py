#!/usr/bin/env python3
"""
Medical Network EPP example: Multi-party communication with delegation.

This example demonstrates:
1. Multi-party trust chains (patient, doctor, cardiologist, wife)
2. Conversation threading across parties
3. Delegation (doctor acts on patient's behalf)
4. Forwarding within a conversation
"""

import json
from datetime import datetime, timedelta, timezone
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
    delegation: dict = None,
) -> dict:
    """Helper to create a signed envelope dict."""
    envelope_id = str(uuid4())
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat().replace("+00:00", "Z")
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
        delegation=delegation,
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
    if delegation:
        envelope_dict["delegation"] = delegation

    # Validate
    Envelope(**envelope_dict)
    return envelope_dict


def main() -> None:
    print("EPP Medical Network Example")
    print("=" * 60)

    # Step 1: Generate keys for all parties
    print("\n1. Generating keys for all parties...")
    patient_key = KeyPair.generate()
    doctor_key = KeyPair.generate()
    cardiologist_key = KeyPair.generate()
    wife_key = KeyPair.generate()

    print(f"   Patient:       {patient_key.public_key_hex()[:24]}...")
    print(f"   Doctor:        {doctor_key.public_key_hex()[:24]}...")
    print(f"   Cardiologist:  {cardiologist_key.public_key_hex()[:24]}...")
    print(f"   Wife:          {wife_key.public_key_hex()[:24]}...")

    # Step 2: Set up trust registries
    print("\n2. Setting up trust registries...")

    # Patient trusts doctor and wife
    patient_trust = TrustRegistry()
    medical_policy = SenderPolicy(
        allowed_scopes=["medical-records", "lab-results", "referral"],
        rate_limit=RateLimit(max_per_hour=50),
    )
    family_policy = SenderPolicy(
        allowed_scopes=["*"],
        rate_limit=RateLimit(max_per_hour=100),
    )
    patient_trust.add_sender(doctor_key.public_key_hex(), "Dr. Smith", medical_policy)
    patient_trust.add_sender(wife_key.public_key_hex(), "Jane (wife)", family_policy)
    print("   Patient trusts: Dr. Smith, Jane (wife)")

    # Doctor trusts cardiologist
    doctor_trust = TrustRegistry()
    specialist_policy = SenderPolicy(
        allowed_scopes=["referral", "consultation"],
        rate_limit=RateLimit(max_per_hour=20),
    )
    doctor_trust.add_sender(
        cardiologist_key.public_key_hex(), "Dr. Heart (Cardiology)", specialist_policy
    )
    print("   Doctor trusts: Dr. Heart (Cardiology)")

    # Wife trusts patient
    wife_trust = TrustRegistry()
    wife_trust.add_sender(
        patient_key.public_key_hex(),
        "Spouse",
        SenderPolicy(allowed_scopes=["*"], rate_limit=RateLimit(max_per_hour=100)),
    )
    print("   Wife trusts: Patient (Spouse)")

    # Step 3: Doctor sends lab results to patient (conversation start)
    print("\n3. Doctor sends lab results to patient...")
    conversation_id = str(uuid4())

    env1 = create_signed_envelope(
        sender_key=doctor_key,
        recipient_hex=patient_key.public_key_hex(),
        scope="lab-results",
        prompt="Your recent blood work results are ready. Key findings: cholesterol "
        "is slightly elevated at 215 mg/dL. I recommend scheduling a follow-up.",
        context={
            "lab_date": "2026-02-05",
            "cholesterol_total": 215,
            "cholesterol_hdl": 55,
            "cholesterol_ldl": 140,
        },
        payload_type="medical-record",
        conversation_id=conversation_id,
    )

    print(f"   Envelope: {env1['envelope_id'][:16]}...")
    print(f"   Conversation: {conversation_id[:16]}...")
    print(f"   Scope: lab-results")
    print(f"   Payload type: medical-record")

    # Step 4: Patient's AI forwards results to wife
    print("\n4. Patient forwards lab results to wife...")

    env2 = create_signed_envelope(
        sender_key=patient_key,
        recipient_hex=wife_key.public_key_hex(),
        scope="lab-results",
        prompt="Sharing my lab results with you. Doctor says cholesterol is slightly "
        "elevated and recommends a follow-up.",
        context=env1["payload"].get("context"),
        payload_type="medical-record",
        conversation_id=conversation_id,
        in_reply_to=env1["envelope_id"],
    )

    print(f"   Envelope: {env2['envelope_id'][:16]}...")
    print(f"   Same conversation: {conversation_id[:16]}...")
    print(f"   In reply to: {env1['envelope_id'][:16]}...")

    # Step 5: Doctor sends referral to cardiologist ON BEHALF OF patient
    print("\n5. Doctor refers patient to cardiologist (delegation)...")
    referral_conversation = str(uuid4())

    delegation = {
        "on_behalf_of": patient_key.public_key_hex(),
        "authorization": "patient-consent-form-2026-02-05",
    }

    env3 = create_signed_envelope(
        sender_key=doctor_key,
        recipient_hex=cardiologist_key.public_key_hex(),
        scope="referral",
        prompt="Referring patient for cardiology consultation. Elevated cholesterol "
        "(215 mg/dL total). Please evaluate and recommend treatment plan.",
        context={
            "patient_id": "P-12345",
            "referring_doctor": "Dr. Smith",
            "reason": "elevated cholesterol",
            "urgency": "routine",
        },
        payload_type="referral",
        conversation_id=referral_conversation,
        delegation=delegation,
    )

    print(f"   Envelope: {env3['envelope_id'][:16]}...")
    print(f"   New conversation: {referral_conversation[:16]}...")
    print(f"   Delegation: on behalf of patient {patient_key.public_key_hex()[:16]}...")
    print(f"   Authorization: patient-consent-form-2026-02-05")

    # Display all envelopes
    print("\n" + "=" * 60)
    print("Summary of all envelopes:")
    print("-" * 60)

    for i, (label, env) in enumerate(
        [
            ("Doctor → Patient (lab results)", env1),
            ("Patient → Wife (forwarded)", env2),
            ("Doctor → Cardiologist (referral, delegated)", env3),
        ],
        1,
    ):
        print(f"\n  {i}. {label}")
        print(f"     ID: {env['envelope_id']}")
        print(f"     Conversation: {env.get('conversation_id', 'N/A')}")
        print(f"     In reply to: {env.get('in_reply_to', 'N/A')}")
        if env.get("delegation"):
            print(f"     Delegation: {env['delegation']['on_behalf_of'][:24]}...")

    print("\n" + "=" * 60)
    print("All envelopes created and validated successfully!")


if __name__ == "__main__":
    main()
