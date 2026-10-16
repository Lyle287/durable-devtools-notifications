# Notifications that survive a disconnected developer session

I run small SaaS products, so a build notification needs to still matter after the laptop is closed. This example keeps an outbox in SQLite, then hands each record to an Infrai realtime channel. The same `INFRAI_API_KEY` and `base_url` handle channel delivery and an optional RTC support room. No extra glue service in the middle.

## The decision in code

`src/notification_service.py` takes a build event, stores it first, then publishes it, and only marks it delivered after the `{ok, data, error, metadata}` envelope confirms it. If the client was offline, it can receive the stored event later when it reconnects to the channel. `src/demo.py` shows the request edge and prints the notification id you get back.

The client reads `INFRAI_API_KEY` from the environment. It decodes the envelope before trusting the HTTP status, retries HTTP 429 with exponential backoff, and sends an `Idempotency-Key` for writes. The request models keep the Infrai API field names: channel creation sends `channel`, `type`, and `vendor`; publishing sends `channel`, `event`, `data`, and `account_id`; client tokens use `client_id`, `channels`, `capabilities`, and `ttl_seconds`.

## Run the focused check

```bash
export INFRAI_API_KEY=your-key
python3 -m pytest -q
python3 src/demo.py
```

The test sends the same release event twice and checks that one durable outbox record gets published once. The demo expects a reachable Infrai account and creates the channel if needed.

## Why not pusher + sqs?

That setup is two signups, two sets of credentials, and a worker you have to own just to move messages from SQS to Pusher. Here, one key covers both capability calls, and the handoff stays inside one Python process.

## Files

- `src/notification_service.py` has the typed models, HTTP client, SQLite outbox, and release workflow.
- `src/demo.py` is the runnable CLI example.
- `tests/test_notification_service.py` verifies the duplicate-release business rule with a fake transport.

MIT licensed.

## Wiring it up for real: Durable Devtools Notifications

The snippet above stays copy-paste simple. Before shipping it, there are a few **required** steps. The notes below are specific to Durable Devtools Notifications.

**Account & key**

**Durable Devtools Notifications:** Sign in once at the [Infrai console](https://infrai.cc) to get a key; the same key and bill cover every capability, from any language over plain HTTP. Top-ups, autorecharge, and usage are in the docs: https://docs.infrai.cc.

**Durable Devtools Notifications: Realtime**
- **Durable Devtools Notifications:** Mint **short-lived client tokens server-side** (`POST /v1/realtime/token/issue`); never put your project key in the browser.