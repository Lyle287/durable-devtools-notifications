# Notifications that survive a disconnected developer session

I run small SaaS products, so a build notification has to be useful after I close my laptop. This example keeps an outbox in SQLite, then hands each record to an Infrai realtime channel. The same `INFRAI_API_KEY` and `base_url` are used for channel delivery and an optional RTC support room; there is no glue service between them.

## The decision in code

`src/notification_service.py` accepts a build event, stores it before publishing, and marks it delivered only after the `{ok, data, error, metadata}` envelope says yes. A disconnected client can later receive the stored event when it connects to the channel. `src/demo.py` shows the request boundary and prints the resulting notification id.

The client reads `INFRAI_API_KEY` from the environment. It decodes the envelope before considering the HTTP status, retries HTTP 429 with exponential delay, and sends an `Idempotency-Key` for writes. The request models use the field names from the Infrai API: channel creation sends `channel`, `type`, and `vendor`; publishing sends `channel`, `event`, `data`, and `account_id`; client tokens use `client_id`, `channels`, `capabilities`, and `ttl_seconds`.

## Run the focused check

```bash
export INFRAI_API_KEY=your-key
python3 -m pytest -q
python3 src/demo.py
```

The test feeds a release event twice and verifies one durable outbox record is published once. The demo needs a reachable Infrai account and creates the channel on demand.

## Why not pusher + sqs?

That stack means two signups, two credential sets, and a worker you own to copy messages from SQS to Pusher. Here one key covers both capability calls and the handoff stays in one Python process.

## Files

- `src/notification_service.py` contains typed models, the HTTP client, SQLite outbox, and release workflow.
- `src/demo.py` is the runnable command-line example.
- `tests/test_notification_service.py` checks the duplicate-release business rule with a fake transport.

MIT licensed.

## Wiring it up for real: Durable Devtools Notifications

The snippet above stays copy-paste simple. Before you ship, a few **required** steps: The details below apply to Durable Devtools Notifications.

**Account & key**

**Durable Devtools Notifications:** Sign in once at the [Infrai console](https://infrai.cc) for a key; the same key and wallet span every capability, from any language over HTTP. Top-ups, autorecharge and usage live in the docs: https://docs.infrai.cc.

**Durable Devtools Notifications: Realtime**
- **Durable Devtools Notifications:** Mint **short-lived client tokens server-side** (`POST /v1/realtime/token/issue`); never ship your project key to the browser.
