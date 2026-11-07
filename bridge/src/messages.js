// Reading and sending iMessages on macOS.
//   inbound:  poll ~/Library/Messages/chat.db (read-only) for new rows after the last ROWID we saw
//   outbound: AppleScript via `osascript` (the Messages app must be signed in)

import { execFile } from "node:child_process";
import { homedir } from "node:os";
import { join } from "node:path";

export const CHAT_DB = process.env.BRIDGE_CHAT_DB || join(homedir(), "Library", "Messages", "chat.db");

/** '(415) 555-0100' / '14155550100' -> '+14155550100'. Emails are lowercased. Mirrors messaging.normalize_phone. */
export function normalize(raw) {
  if (!raw) return "";
  const s = String(raw).trim();
  if (s.includes("@")) return s.toLowerCase();
  let digits = s.replace(/\D/g, "");
  if (digits.length === 10) digits = "1" + digits;
  return digits ? `+${digits}` : "";
}

/**
 * Newer macOS versions leave `message.text` NULL and store the text in `attributedBody`, a
 * serialized NSAttributedString. The plain string follows the "NSString" class marker, prefixed
 * by a length byte (or 0x81 + 2-byte little-endian length for long messages).
 */
export function textFromAttributedBody(buf) {
  if (!buf) return null;
  const b = Buffer.from(buf);
  const marker = b.indexOf("NSString");
  if (marker < 0) return null;
  let i = marker + "NSString".length;
  const plus = b.indexOf(0x2b, i); // '+' precedes the length
  if (plus < 0 || plus - i > 8) return null;
  i = plus + 1;
  let len = b[i];
  i += 1;
  if (len === 0x81) {
    len = b.readUInt16LE(i);
    i += 2;
  } else if (len === 0x82) {
    len = b.readUIntLE(i, 3);
    i += 3;
  }
  const text = b.subarray(i, i + len).toString("utf8").trim();
  return text || null;
}

export async function openDb() {
  const { default: Database } = await import("better-sqlite3");
  return new Database(CHAT_DB, { readonly: true, fileMustExist: true });
}

export function maxRowId(db) {
  return db.prepare("SELECT IFNULL(MAX(ROWID), 0) AS id FROM message").get().id;
}

/** Inbound messages (not sent by us) newer than `afterRowId`, oldest first. */
export function newMessages(db, afterRowId) {
  const rows = db
    .prepare(
      `SELECT m.ROWID AS rowid, m.text, m.attributedBody AS body, h.id AS sender
         FROM message m LEFT JOIN handle h ON h.ROWID = m.handle_id
        WHERE m.ROWID > ? AND m.is_from_me = 0 AND m.item_type = 0
        ORDER BY m.ROWID ASC LIMIT 50`,
    )
    .all(afterRowId);
  return rows.map((r) => ({
    rowid: r.rowid,
    sender: normalize(r.sender),
    text: (r.text ?? textFromAttributedBody(r.body) ?? "").trim(),
  }));
}

/** AppleScript string literal: escape backslashes and quotes. */
export function asString(s) {
  return `"${String(s).replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"`;
}

export function sendScript(to, text) {
  return [
    'tell application "Messages"',
    "  set svc to 1st account whose service type = iMessage",
    `  set buddyRef to participant ${asString(to)} of svc`,
    `  send ${asString(text)} to buddyRef`,
    "end tell",
  ].join("\n");
}

export function sendIMessage(to, text) {
  return new Promise((resolve) => {
    execFile("osascript", ["-e", sendScript(to, text)], { timeout: 15000 }, (err, _out, stderr) => {
      if (err) {
        console.error(`[bridge] send to ${to} failed: ${stderr || err.message}`);
        resolve(false);
      } else resolve(true);
    });
  });
}
