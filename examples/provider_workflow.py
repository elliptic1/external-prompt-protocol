#!/usr/bin/env python3
"""
Provider Workflow Example

Demonstrates how a professional (lawyer) interacts with their AI concurrently:

1. Lawyer's AI receives a consultation from a client
2. AI creates/updates case in memory
3. AI has questions for the lawyer
4. Lawyer reviews cases and provides guidance
5. Next consultation uses the updated case knowledge

The lawyer talks to their AI whenever they have time.
The AI learns from their guidance and applies it to future consultations.
"""

from datetime import datetime, timezone

# EPP core imports
from epp.crypto.keys import KeyPair

# Services layer (example implementation, not part of EPP core)
from services.services import (
    CaseRecord,
    CaseMemory,
    ProviderSession,
    ServiceRequest,
    ServiceResponse,
    create_case_record,
    create_case_memory,
    create_provider_session,
    create_legal_consultation_listing,
)


def main():
    print("=" * 70)
    print("EPP Provider Workflow Example")
    print("=" * 70)
    print()

    # ==========================================================================
    # SETUP: Generate keys
    # ==========================================================================
    lawyer_keypair = KeyPair.generate()
    lawyer_public = lawyer_keypair.public_key_hex()

    client1_keypair = KeyPair.generate()
    client1_public = client1_keypair.public_key_hex()

    client2_keypair = KeyPair.generate()
    client2_public = client2_keypair.public_key_hex()

    # ==========================================================================
    # Initialize the lawyer's AI with case memory
    # ==========================================================================
    print("Step 1: Initialize Lawyer's AI with Case Memory")
    print("-" * 40)

    case_memory = create_case_memory(provider=lawyer_public)
    print(f"Case memory initialized for provider: {lawyer_public[:16]}...")
    print()

    # ==========================================================================
    # Client 1 sends a consultation request
    # ==========================================================================
    print("Step 2: Client 1 sends consultation request")
    print("-" * 40)

    request1 = ServiceRequest(
        service_id="legal-service-001",
        client=client1_public,
        query="""
        My employer laid me off after I filed a complaint about unpaid overtime.
        They said it was due to 'restructuring' but I was the only one let go.
        Two weeks later they hired someone new for my position.
        """.strip(),
        context={
            "location": "California",
            "employment_status": "terminated",
            "category": "employment-retaliation",
        },
    )

    print(f"Client 1 query: {request1.query[:60]}...")
    print()

    # Lawyer's AI processes the request
    # First, check for existing case context
    case_context = case_memory.get_context_for_request(request1)
    print(f"Existing case context: {case_context is not None}")

    # AI generates initial response
    response1 = ServiceResponse(
        request_id=request1.request_id,
        service_id=request1.service_id,
        provider=lawyer_public,
        response="""
        Based on your description, you may have grounds for a wrongful termination
        and retaliation claim under California Labor Code Section 98.6.
        """.strip(),
        confidence=0.75,  # Lower confidence - AI wants to ask lawyer
    )

    # AI creates/updates case in memory
    case1 = case_memory.create_or_update_case_from_request(request1, response1)
    print(f"Case created: {case1.case_id[:16]}...")
    print(f"Case title: {case1.title}")

    # AI adds facts from the consultation
    case1.add_fact("Client filed overtime complaint before termination")
    case1.add_fact("Client was only employee terminated in 'restructuring'")
    case1.add_fact("Employer hired replacement within 2 weeks")
    case1.add_fact("Location: California")

    # AI has questions for the lawyer
    case1.add_ai_question(
        "Should I recommend filing with DLSE or suggesting private attorney first?"
    )
    case1.add_ai_question(
        "What's the typical timeline for retaliation claims in CA?"
    )

    print(f"Facts recorded: {len(case1.facts)}")
    print(f"AI questions: {len(case1.ai_questions)}")
    print()

    # ==========================================================================
    # Client 2 sends a different consultation request
    # ==========================================================================
    print("Step 3: Client 2 sends consultation request")
    print("-" * 40)

    request2 = ServiceRequest(
        service_id="legal-service-001",
        client=client2_public,
        query="""
        I'm a contractor and my client hasn't paid me for 3 months of work.
        The contract says payment is due within 30 days. Total owed is $45,000.
        They keep saying the check is coming but nothing arrives.
        """.strip(),
        context={
            "category": "contract-dispute",
            "amount_owed": 45000,
        },
    )

    print(f"Client 2 query: {request2.query[:60]}...")

    # Process and create case
    response2 = ServiceResponse(
        request_id=request2.request_id,
        service_id=request2.service_id,
        provider=lawyer_public,
        response="Contract breach case - recommend demand letter followed by small claims or civil action.",
        confidence=0.80,
    )

    case2 = case_memory.create_or_update_case_from_request(request2, response2)
    case2.add_fact("Contractor relationship")
    case2.add_fact("3 months unpaid")
    case2.add_fact("$45,000 owed")
    case2.add_fact("Contract specifies 30-day payment terms")

    case2.add_ai_question(
        "Should I recommend small claims ($10k limit) or civil court for $45k?"
    )

    print(f"Case created: {case2.case_id[:16]}...")
    print()

    # ==========================================================================
    # LATER: Lawyer reviews cases and provides guidance
    # ==========================================================================
    print("=" * 70)
    print("LAWYER'S TURN: Provider Session")
    print("=" * 70)
    print()

    # Lawyer starts a session with their AI
    provider_session = create_provider_session(provider=lawyer_public)
    print(f"Provider session started: {provider_session.session_id[:16]}...")
    print()

    # AI presents cases with pending questions
    cases_with_questions = case_memory.find_cases_with_questions()
    print(f"Cases needing attention: {len(cases_with_questions)}")
    print()

    # Simulate the conversation
    for case in cases_with_questions:
        print(f"📁 Case: {case.title}")
        print(f"   Status: {case.status} | Priority: {case.priority}")
        print(f"   Facts: {len(case.facts)} | Notes: {len(case.notes)}")
        print()

        for i, q in enumerate(case.ai_questions):
            if not q.get("answered", False):
                print(f"   ❓ AI Question: {q['question']}")

                # AI sends message
                provider_session.add_message(
                    role="ai",
                    content=f"Regarding case {case.case_id[:8]}: {q['question']}",
                    case_refs=[case.case_id],
                )

                # Simulate lawyer's answer based on case
                if "employment-retaliation" in case.category:
                    if "DLSE" in q["question"]:
                        answer = """
                        For retaliation cases, I recommend starting with DLSE because:
                        1. It's free for the client
                        2. DLSE investigators can compel evidence
                        3. If DLSE doesn't resolve it, they can still hire private counsel
                        
                        Only recommend private attorney first if client wants faster resolution
                        or the case is particularly complex.
                        """.strip()
                    else:
                        answer = """
                        Typical timeline for CA retaliation claims:
                        - DLSE investigation: 6-18 months
                        - Settlement negotiation: 2-6 months
                        - If litigation: 1-2 years
                        
                        Statute of limitations is 1 year from termination, so urge
                        clients to file promptly.
                        """.strip()
                else:
                    answer = """
                    For $45k, civil court is the way to go. Small claims max in CA is $10k.
                    Recommend sending a formal demand letter first (14-day deadline),
                    then file in civil court if no response. Mention attorney fees
                    clause if contract has one.
                    """.strip()

                # Lawyer provides answer
                case.answer_ai_question(i, answer)
                provider_session.add_message(
                    role="provider",
                    content=answer,
                    case_refs=[case.case_id],
                    action_taken="answered_question",
                )

                print(f"   ✅ Lawyer answered: {answer[:60]}...")
                print()

    # Lawyer adds some general guidance
    print("-" * 40)
    print("Lawyer adds case-specific guidance:")
    print()

    case1.add_guidance(
        "For this specific case: Strong retaliation facts. "
        "Recommend DLSE filing within 30 days."
    )
    case1.priority = "high"
    provider_session.record_decision(
        case_id=case1.case_id,
        decision="Recommend DLSE filing",
        rationale="Strong temporal connection between complaint and termination",
    )

    print(f"✓ Case 1 priority upgraded to: {case1.priority}")
    print(f"✓ Guidance added: {case1.guidance[-1][:50]}...")
    print()

    case2.add_guidance(
        "Standard contract dispute. Demand letter template #3. "
        "If no response in 14 days, prepare civil filing."
    )
    provider_session.record_decision(
        case_id=case2.case_id,
        decision="Standard demand letter approach",
        rationale="Clear breach, documented terms",
    )

    print(f"✓ Case 2 guidance added")
    print()

    # End provider session
    provider_session.end_session()
    print(f"Provider session ended. Decisions made: {len(provider_session.decisions_made)}")
    print()

    # ==========================================================================
    # LATER: Client 1 sends follow-up (now has enriched context)
    # ==========================================================================
    print("=" * 70)
    print("FOLLOW-UP: Client 1 returns with question")
    print("=" * 70)
    print()

    request1_followup = ServiceRequest(
        service_id="legal-service-001",
        client=client1_public,  # Same client
        query="Should I file with the state or hire a lawyer directly?",
        context={"follow_up": True},
    )

    # Now the AI has case context with lawyer's guidance
    case_context = case_memory.get_context_for_request(request1_followup)
    print("Case context available for follow-up:")
    print(f"  - Case ID: {case_context['case_id'][:16]}...")
    print(f"  - Priority: {case_context['priority']}")
    print(f"  - Facts: {len(case_context['facts'])}")
    print(f"  - Guidance: {len(case_context['guidance'])}")
    print()

    print("Guidance from lawyer (now available to AI):")
    for g in case_context['guidance']:
        print(f"  → {g}")
    print()

    # AI can now give a confident, lawyer-informed response
    response1_followup = ServiceResponse(
        request_id=request1_followup.request_id,
        service_id=request1_followup.service_id,
        provider=lawyer_public,
        response=f"""
        Based on your case specifics, I recommend filing with the California DLSE 
        (Division of Labor Standards Enforcement) first. Here's why:

        1. **It's free** - No attorney fees required to start
        2. **They can compel evidence** - DLSE investigators have subpoena power
        3. **Strong case** - The timing between your overtime complaint and 
           termination creates a strong presumption of retaliation

        The attorney reviewing your case noted: "{case_context['guidance'][0]}"

        If DLSE doesn't resolve it satisfactorily, you can still hire a private 
        attorney later. Many employment lawyers work on contingency for cases 
        like yours.

        Would you like guidance on how to file with the DLSE?
        """.strip(),
        confidence=0.95,  # Much higher confidence with lawyer's input
    )

    # Link follow-up to case
    case1.link_consultation(request1_followup.request_id)

    print(f"AI response confidence: {response1_followup.confidence}")
    print(f"Response includes lawyer's guidance: Yes")
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print()
    print("The lawyer talked to their AI about current cases.")
    print("The AI learned from the lawyer's decisions and guidance.")
    print("Future consultations now benefit from that knowledge.")
    print()
    print(f"Total cases in memory: {len(case_memory.cases)}")
    print(f"Cases with guidance: {sum(1 for c in case_memory.cases.values() if c.guidance)}")
    print(f"Provider session decisions: {len(provider_session.decisions_made)}")


if __name__ == "__main__":
    main()
