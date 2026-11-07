// Runway iMessage bridge (macOS only).
//
// Inbound:  polls the local Messages database and forwards new messages to
//           POST {RUNWAY_API_URL}/imessage/inbound  { sender, text }
// Outbound: the API calls POST /send { to, text } and we send via Messages.
//
// Needs Full Disk Access for the terminal running it (System Settings → Privacy & Security)
// to read incoming messages. Sending works without it.
//
// /send and /inbound require `X-Runway-Token: $RUNWAY_API_TOKEN` (the same token the API uses).
// Without a token set, they only answer direct local requests: anything arriving through a tunnel
// (it carries X-Forwarded-For / CF-Connecting-IP) is refused, so an exposed bridge can't be used to
// send texts from this Mac or to approve things as the founder.

import { timingSafeEqual } from "node:crypto";

import express from "express";
import { IMessageSDK, asRecipient } from "@photon-ai/imessage-kit";

const PORT = Number(process.env.BRIDGE_PORT || 3099);
const API_URL = (process.env.RUNWAY_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
const API_TOKEN = process.env.RUNWAY_API_TOKEN || "";
const POLL_MS = Number(process.env.BRIDGE_POLL_MS || 5000);
// Only forward messages from these senders (comma-separated). Empty = forward everything.
const ALLOW = (process.env.BRIDGE_ALLOWED_SENDERS || "").split(",").map((s) => s.trim()).filter(Boolean);

const sdk = new IMessageSDK({ debug: false, maxConcurrent: 5 });
const seen = new Set();
let canRead = true;
let busy = false;

process.on("unhandledRejection", (reason) => {
  if (String(reason).includes("database")) {
    canRead = false;
    console.warn("[bridge] Can't read Messages DB (grant Full Disk Access). Sending still works.");
  } else {
    console.error("[bridge] unhandled rejection:", reason);
  }
});

const listMessages = async (limit) => {
  const r = await sdk.getMessages({ limit, excludeOwnMessages: false });
  return Array.isArray(r) ? r : r?.messages || [];
};

async function forward(msg) {
  const res = await fetch(`${API_URL}/imessage/inbound`, {
    method: "POST",
    headers: { "content-type": "application/json", ...(API_TOKEN && { "x-runway-token": API_TOKEN }) },
    body: JSON.stringify({ sender: msg.sender || "", text: msg.text || "" }),
  });
  if (!res.ok) console.warn(`[bridge] API answered ${res.status}`);
}

async function poll() {
  if (!canRead || busy) return;
  busy = true;
  try {
    for (const msg of (await listMessages(50)).reverse()) {
      if (msg.isFromMe || !msg.id || seen.has(msg.id)) continue;
      seen.add(msg.id);
      if (ALLOW.length && !ALLOW.includes(msg.sender)) continue;
      await forward(msg).catch((e) => console.warn("[bridge] API unreachable:", e.message));
      console.log(`[bridge] → API: message from ${msg.sender}`);
    }
  } catch (e) {
    if (String(e).toLowerCase().includes("database")) canRead = false;
    else console.warn("[bridge] poll failed:", e.message);
  } finally {
    busy = false;
  }
}

// Mark everything already in the DB as seen so we only forward new messages.
try {
  for (const m of await listMessages(500)) if (m.id) seen.add(m.id);
  console.log(`[bridge] ignoring ${seen.size} existing messages`);
} catch {
  canRead = false;
  console.warn("[bridge] Can't read Messages DB; inbound disabled. POST /inbound to simulate.");
}
setInterval(poll, POLL_MS);

const app = express();
app.use(express.json());

const validRecipient = (v) => typeof v === "string" && (/^\+\d{10,15}$/.test(v) || /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v));

app.get("/health", (_req, res) => res.json({ ok: true, canRead, seen: seen.size }));

const sameToken = (given) => {
  const a = Buffer.from(String(given || ""));
  const b = Buffer.from(API_TOKEN);
  return a.length === b.length && timingSafeEqual(a, b);
};
const viaProxy = (req) => Boolean(req.get("x-forwarded-for") || req.get("cf-connecting-ip") || req.get("forwarded"));

function requireToken(req, res, next) {
  if (API_TOKEN) {
    if (sameToken(req.get("x-runway-token"))) return next();
    return res.status(401).json({ ok: false, error: "missing or wrong X-Runway-Token" });
  }
  if (viaProxy(req)) {
    return res.status(403).json({ ok: false, error: "set RUNWAY_API_TOKEN before exposing the bridge" });
  }
  return next(); // local dev: no token, direct request from this machine
}

app.post("/send", requireToken, async (req, res) => {
  const { to, text } = req.body || {};
  if (!validRecipient(to) || !text) return res.status(400).json({ ok: false, error: "need to (E.164 or email) and text" });
  try {
    await sdk.send(asRecipient(to), String(text));
    res.json({ ok: true });
  } catch (e) {
    res.status(500).json({ ok: false, error: String(e) });
  }
});

// Testing without a Mac Messages DB: curl -XPOST localhost:3099/inbound -d '{"sender":"+1...","text":"y"}'
app.post("/inbound", requireToken, async (req, res) => {
  try {
    await forward(req.body || {});
    res.json({ ok: true });
  } catch (e) {
    res.status(502).json({ ok: false, error: String(e) });
  }
});

app.listen(PORT, "127.0.0.1", () => {
  console.log(`[bridge] listening on http://127.0.0.1:${PORT} → ${API_URL}`);
  if (!API_TOKEN) console.warn("[bridge] RUNWAY_API_TOKEN is not set: /send and /inbound only accept local requests.");
});
