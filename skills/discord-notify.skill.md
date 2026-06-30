name: discord-notify
description: |
  Sends a simple text message (or optional embed) to a Discord channel via a webhook.
  The webhook URL is stored in Hermes memory under the key `discord_webhook_url`.
  If not found, the skill falls back to the environment variable DISCORD_WEBHOOK.
categories: [social-media, automation, web]
steps:
  1. Retrieve the webhook URL:
        - Try `memory_get` for key `discord_webhook_url`.
        - If missing, read environment variable `DISCORD_WEBHOOK`.
        - If still empty, return error `{ "status":"error", "message":"Discord webhook URL not configured" }`.
  2. Build the JSON payload:
        { "content": "<provided text>" }
        If an optional `embed` field is supplied (as JSON string), merge it into the payload.
  3. Use `execute_code` to perform an HTTP POST to the webhook URL with the payload
        (Content-Type: application/json). Capture the response.
  4. If the response status code is 200‑204, return `{ "status":"ok" }`.
        Otherwise return `{ "status":"error", "message":<response body> }`.