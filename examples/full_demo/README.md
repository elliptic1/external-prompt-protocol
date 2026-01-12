# EPP Full Demo: Coffee Shop & App Store

This example demonstrates a complete EPP workflow with two senders (a coffee shop and an app store) delivering prompts to your personal AI inbox.

## Scenario

You're a developer who:
1. Frequents a local coffee shop that knows your usual order
2. Has an app pending review in an app store

Both businesses have your EPP public key and permission to send you prompts within specific scopes.

```
┌─────────────────┐     ┌─────────────────┐
│  Coffee Shop    │     │   App Store     │
│  (retail scope) │     │ (app-review)    │
└────────┬────────┘     └────────┬────────┘
         │                       │
         │   Signed Envelopes    │
         ▼                       ▼
    ┌─────────────────────────────────┐
    │         YOUR EPP INBOX          │
    │  ┌───────────────────────────┐  │
    │  │ Trust Registry:           │  │
    │  │ - Coffee Shop ✓ (retail)  │  │
    │  │ - App Store ✓ (app-review)│  │
    │  └───────────────────────────┘  │
    └─────────────────────────────────┘
                    │
                    ▼
             ┌──────────────┐
             │   Your AI    │
             │  (executor)  │
             └──────────────┘
```

## Files in This Demo

| File | Purpose |
|------|---------|
| `1_setup.py` | Generate keys for all parties |
| `2_configure_inbox.py` | Set up trust registry and policies |
| `3_run_inbox.py` | Start the EPP inbox server |
| `4_coffee_shop_sends.py` | Coffee shop sends a promotional prompt |
| `5_app_store_sends.py` | App store sends a rejection notice |
| `6_check_queue.py` | View received and queued prompts |
| `config.yaml` | Inbox server configuration |

## Step-by-Step Walkthrough

### Step 1: Setup Keys

First, generate Ed25519 key pairs for everyone involved.

```bash
python 1_setup.py
```

This creates:
```
keys/
├── inbox.key          # Your inbox private key (keep secret!)
├── inbox.pub          # Your inbox public key (share with senders)
├── coffee_shop.key    # Coffee shop's private key
├── coffee_shop.pub    # Coffee shop's public key
├── app_store.key      # App store's private key
└── app_store.pub      # App store's public key
```

**What's happening:**
- Each party gets an Ed25519 key pair
- Private keys are used to sign envelopes
- Public keys identify senders and recipients
- Keys are 32 bytes, displayed as 64-character hex strings

### Step 2: Configure the Inbox

Add trusted senders to your inbox's trust registry.

```bash
python 2_configure_inbox.py
```

This creates a trust registry with:
- **Coffee Shop**: Allowed scopes `retail`, `promotions`. Max 10/hour, 50/day.
- **App Store**: Allowed scopes `app-review`, `account`. Max 5/hour, 20/day.

**What's happening:**
- You explicitly trust each sender's public key
- Each sender is restricted to specific scopes
- Rate limits prevent spam
- Untrusted senders are rejected

### Step 3: Start the Inbox Server

Run the EPP inbox to receive envelopes.

```bash
python 3_run_inbox.py
```

The server:
- Listens on `http://localhost:8000`
- Exposes `/epp/v1/submit` for envelope submission
- Verifies signatures against the trust registry
- Queues accepted prompts for your AI

**What's happening:**
- FastAPI server starts with your inbox keys loaded
- Incoming envelopes are validated in this order:
  1. JSON structure valid?
  2. Version supported?
  3. Addressed to this inbox?
  4. Not expired?
  5. Signature valid?
  6. Nonce not replayed?
  7. Sender trusted?
  8. Scope allowed for this sender?
  9. Size within limits?
  10. Rate limit not exceeded?
- Accepted envelopes go to the file queue executor

### Step 4: Coffee Shop Sends a Prompt

In a new terminal, simulate the coffee shop sending you a promotion.

```bash
python 4_coffee_shop_sends.py
```

The coffee shop creates an envelope:
```json
{
  "version": "1",
  "sender": "<coffee_shop_public_key>",
  "recipient": "<your_inbox_public_key>",
  "scope": "retail",
  "payload": {
    "prompt": "Your usual vanilla oat latte is ready! 20% off today.",
    "context": {
      "store_name": "Bean Counter Coffee",
      "offer_code": "LOYAL20",
      "valid_until": "2025-01-12T17:00:00Z"
    }
  },
  "signature": "<ed25519_signature>"
}
```

**What's happening:**
1. Coffee shop loads its private key
2. Creates envelope with prompt and context
3. Signs the envelope (proves it's really from them)
4. POSTs to your inbox
5. Inbox verifies and queues for your AI

### Step 5: App Store Sends a Rejection

Simulate the app store sending a rejection notice.

```bash
python 5_app_store_sends.py
```

The app store creates an envelope:
```json
{
  "scope": "app-review",
  "payload": {
    "prompt": "Your app 'WeatherWidget' was rejected.",
    "context": {
      "app_id": "com.example.weatherwidget",
      "rejection_reason": "Guideline 4.2 - Minimum Functionality",
      "details": "App appears to be a simple web wrapper...",
      "appeal_deadline": "2025-01-19T00:00:00Z"
    }
  }
}
```

**What's happening:**
- Same flow as coffee shop
- Different scope (`app-review` instead of `retail`)
- Your AI receives structured data about the rejection
- AI could analyze the issue and suggest fixes

### Step 6: Check the Queue

See what prompts your AI has received.

```bash
python 6_check_queue.py
```

Output:
```
=== Queued Envelopes ===

[1] From: Coffee Shop (Bean Counter Coffee)
    Scope: retail
    Prompt: Your usual vanilla oat latte is ready! 20% off today.
    Received: 2025-01-12T10:30:00Z

[2] From: App Store
    Scope: app-review
    Prompt: Your app 'WeatherWidget' was rejected.
    Received: 2025-01-12T10:31:00Z
```

**What's happening:**
- The file queue executor wrote each envelope to a JSON file
- Your AI would read these and decide how to handle them
- Maybe the coffee deal gets a low-priority notification
- Maybe the app rejection triggers immediate analysis

---

## What Your AI Does Next

EPP delivers the prompts. What happens next is up to you.

**Coffee shop prompt → Your AI might:**
- Check if you're near the coffee shop (location context)
- Consider your calendar (are you busy?)
- Whisper via your earbuds: "Coffee shop has your usual ready, 20% off"

**App store prompt → Your AI might:**
- Analyze the rejection reason against Apple's guidelines
- Search your codebase for the issue
- Draft an appeal or suggest code changes
- Alert you immediately (high priority)

---

## Security in Action

### What EPP Prevents

| Attack | How EPP Stops It |
|--------|------------------|
| Impersonation | Signature verification against known public key |
| Replay | Nonce tracking + expiration timestamps |
| Spam | Rate limits per sender |
| Scope creep | Sender can only use allowed scopes |
| Unauthorized sender | Must be in trust registry |

### Try Breaking It

1. **Modify an envelope after signing** → Signature verification fails
2. **Replay a valid envelope** → Nonce already seen
3. **Send from untrusted key** → Sender not in trust registry
4. **Use wrong scope** → Policy denies the scope
5. **Exceed rate limit** → Rate limiter blocks it

---

## Running the Full Demo

```bash
# Terminal 1: Setup and start inbox
cd examples/full_demo
python 1_setup.py
python 2_configure_inbox.py
python 3_run_inbox.py

# Terminal 2: Send prompts
python 4_coffee_shop_sends.py
python 5_app_store_sends.py
python 6_check_queue.py
```

---

## Next Steps

- **Customize executors**: Instead of file queue, pipe to your actual AI
- **Add more senders**: Banks, airlines, healthcare providers
- **Use Solana transport**: No server needed (see `solana_example.py`)
- **Build a wearable client**: Poll for prompts, whisper to user

---

## Troubleshooting

**"UNTRUSTED_SENDER" error**
- Sender's public key not in trust registry
- Run `python 2_configure_inbox.py` to add them

**"INVALID_SIGNATURE" error**
- Envelope was modified after signing
- Or wrong private key was used

**"POLICY_DENIED" error**
- Sender tried to use a scope they're not allowed
- Check the trust registry configuration

**"RATE_LIMITED" error**
- Sender exceeded their hourly/daily limit
- Wait or increase limits in trust registry
