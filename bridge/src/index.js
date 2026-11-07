// Runway iMessage bridge (macOS).
//
//   Messages.app ──(chat.db poll)──▶ POST {RUNWAY_API_URL}/imessage/inbound
//   Runway API   ──POST /send──────▶ osascript ──▶ Messages.app
//
// The API sends its replies through POST /send (RUNWAY_NOTIFIER=imessage), so the bridge never
// texts anything on its own. Only senders in BRIDGE_ALLOWED_SENDERS (plus the founder) are forwarded.

import { createServer } from "node:http";

import { maxRowId, newMessages, normalize, openDb, sendIMessage } from "./messages.js";

const API_URL = (process.env.RUNWAY_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
const API_TOKEN = process.env.RUNWAY_API_TOKEN || "";
const PORT = Number(process.env.BRIDGE_PORT || 3099);
const HOST = process.env.BRIDGE_HOST || "127.0.0.1";
const POLL_MS = Number(process.env.BRIDGE_POLL_MS || 2000);
const ALLOWED = new Set(
  [process.env.RUNWAY_FOUNDER_PHONE, ...(process.env.BRIDGE_ALLOWED_SENDERS || "").split(",")]
    .map(normalize)
    .filter(Boolean),
);

function allowed(sender) {
  return ALLOWED.size === 0 || ALLOWED.has(normalize(sender));
}

async function forward(msg) {
  try {
    const r = await fetch(`${API_URL}/imessage/inbound`, {
      method: "POST",
      headers: { "content-type": "application/json", ...(API_TOKEN && { "x-runway-token": API_TOKEN }) },
      body: JSON.stringify({ text: msg.text, sender: msg.sender }),
    });
    if (!r.ok) console.error(`[bridge] API returned ${r.status} for message ${msg.rowid}`);
    return r.ok;
  } catch (e) {
    console.error(`[bridge] API unreachable (${API_URL}): ${e.message}`);
    return false;
  }
}

async function pollLoop() {
  const db = await openDb();
  let last = maxRowId(db); // start from "now": never replay old conversations on boot
  console.log(`[bridge] watching Messages from ROWID ${last}; forwarding to ${API_URL}`);
  for (;;) {
    try {
      for (const msg of newMessages(db, last)) {
        if (msg.text && allowed(msg.sender)) {
          console.log(`[bridge] ← ${msg.sender}: ${msg.text.slice(0, 80)}`);
          if (!(await forward(msg))) break; // API down: retry this message on the next poll
        }
        last = msg.rowid;
      }
    } catch (e) {
      console.error(`[bridge] poll failed: ${e.message}`);
    }
    await new Promise((r) => setTimeout(r, POLL_MS));
  }
}

function readJson(req) {
  return new Promise((resolve, reject) => {
    let data = "";
    req.on("data", (c) => {
      data += c;
      if (data.length > 64_000) reject(new Error("body too large"));
    });
    req.on("end", () => {
      try {
        resolve(JSON.parse(data || "{}"));
      } catch (e) {
        reject(e);
      }
    });
  });
}

function reply(res, status, body) {
  res.writeHead(status, { "content-type": "application/json" });
  res.end(JSON.stringify(body));
}

const server = createServer(async (req, res) => {
  if (req.method === "GET" && req.url === "/health") return reply(res, 200, { ok: true });
  if (req.method !== "POST" || req.url !== "/send") return reply(res, 404, { ok: false });
  try {
    const { to, text } = await readJson(req);
    if (!to || !text) return reply(res, 400, { ok: false, error: "need to and text" });
    console.log(`[bridge] → ${to}: ${String(text).slice(0, 80)}`);
    return reply(res, 200, { ok: await sendIMessage(to, text) });
  } catch (e) {
    return reply(res, 400, { ok: false, error: e.message });
  }
});

if (process.platform !== "darwin") {
  console.error("[bridge] iMessage needs macOS. Use RUNWAY_NOTIFIER=console elsewhere.");
  process.exit(1);
}
server.listen(PORT, HOST, () => console.log(`[bridge] send endpoint on http://${HOST}:${PORT}/send`));
pollLoop().catch((e) => {
  console.error(`[bridge] can't read ${e.message}. Give your terminal Full Disk Access (System Settings → Privacy).`);
  process.exit(1);
});
