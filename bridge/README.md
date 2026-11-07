# iMessage bridge

Tiny Node service that connects the Mac's Messages app to the Runway API. Only needed when
you want real iMessages; everyone else can use `RUNWAY_NOTIFIER=console`.

```bash
npm install
npm run dev            # reads ../.env
```

- Grant **Full Disk Access** to your terminal (System Settings → Privacy & Security) so it can read incoming messages.
- Set `RUNWAY_NOTIFIER=imessage` and `RUNWAY_FOUNDER_PHONE` in `.env` so the API sends through it.
- Set `BRIDGE_ALLOWED_SENDERS` to the founder's and employees' numbers so random texts to the demo Mac aren't forwarded.
- If the API is on AWS, set `RUNWAY_API_URL` to the API Gateway URL and `RUNWAY_API_TOKEN` to match. The bridge
  itself always runs on a Mac (iMessage has no cloud API).
