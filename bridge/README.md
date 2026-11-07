# iMessage bridge

Connects the Messages app on a Mac to the Runway API. macOS only (iMessage can't run in AWS).

```
Messages.app ──(polls chat.db)──▶ POST $RUNWAY_API_URL/imessage/inbound
Runway API   ──POST :3099/send──▶ osascript ──▶ Messages.app
```

The bridge only forwards messages and delivers what the API asks it to send. All logic lives in
`backend/runway/conversation.py`.

## Setup (demo Mac)

1. Sign in to Messages with the Apple ID that will text the founder.
2. Give your terminal app **Full Disk Access** (System Settings → Privacy & Security), so it can
   read `~/Library/Messages/chat.db`. The first send will also ask to let the terminal control Messages.
3. In the repo's `.env`:
   ```
   RUNWAY_NOTIFIER=imessage
   RUNWAY_FOUNDER_PHONE=+15551234567
   RUNWAY_IMESSAGE_BRIDGE_URL=http://127.0.0.1:3099
   RUNWAY_API_URL=http://127.0.0.1:8000
   BRIDGE_ALLOWED_SENDERS=+15557654321   # employees who may text Runway (founder is always allowed)
   ```
4. Run it (Node 20+):
   ```bash
   make api       # terminal 1
   make bridge    # terminal 2 (npm install happens in make setup)
   curl -X POST localhost:8000/hello   # you should get the boot greeting by iMessage
   ```

## With the API on AWS

Point `RUNWAY_API_URL` at the `ApiUrl` output and set `RUNWAY_API_TOKEN` to the deployed token
(`deploy.sh` saves it in `.runway-token` at the repo root). For replies, Lambda must reach `/send`:
expose port 3099 with a tunnel (`cloudflared tunnel --url http://localhost:3099`) and deploy with
`BridgeUrl=<tunnel url>`.

**Set the token before opening the tunnel.** `/send` requires `X-Runway-Token: $RUNWAY_API_TOKEN`
(the API sends it automatically), so nobody who finds the tunnel URL can text from this Mac. With no
token set, `/send` only accepts direct local requests and refuses anything that came through a tunnel.
If the token is rotated, update it here too, or replies fail with a 401 (logged by the API).

Inbound messages are read from `chat.db`, so there is no inbound HTTP endpoint to protect.

## Settings

| Variable | Default | |
|---|---|---|
| `RUNWAY_API_URL` | `http://127.0.0.1:8000` | where inbound messages go |
| `RUNWAY_API_TOKEN` | | sent as `X-Runway-Token` to the API, and required on `/send` |
| `BRIDGE_PORT` / `BRIDGE_HOST` | `3099` / `127.0.0.1` | the `/send` endpoint |
| `BRIDGE_POLL_MS` | `2000` | how often to check for new messages |
| `BRIDGE_ALLOWED_SENDERS` | | comma-separated; empty + no founder phone = forward everyone |
| `BRIDGE_CHAT_DB` | `~/Library/Messages/chat.db` | |

On start the bridge skips everything already in `chat.db`, so old conversations are never replayed.
If the API is down, the message is retried on the next poll.

`npm test` runs the unit tests (these work on any OS).
