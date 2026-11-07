// Who may use the bridge's /send endpoint.
//
// With RUNWAY_API_TOKEN set (the same token the API uses), a request must carry it in
// X-Runway-Token. Without one, only direct local requests are allowed: anything that came through
// a tunnel or proxy (it carries X-Forwarded-For / CF-Connecting-IP / Forwarded) is refused, so
// forgetting the token fails closed instead of letting anyone send texts from this Mac.

import { timingSafeEqual } from "node:crypto";

const PROXY_HEADERS = ["x-forwarded-for", "cf-connecting-ip", "forwarded", "x-real-ip"];

/** Constant-time string compare (so the token can't be guessed byte by byte from response times). */
export function sameSecret(given, expected) {
  const a = Buffer.from(String(given ?? ""));
  const b = Buffer.from(String(expected ?? ""));
  return a.length === b.length && b.length > 0 && timingSafeEqual(a, b);
}

/** `headers` is a Node IncomingMessage.headers object (lower-cased keys). Returns null if allowed. */
export function authorize(headers, token) {
  if (token) {
    return sameSecret(headers["x-runway-token"], token)
      ? null
      : { status: 401, error: "missing or wrong X-Runway-Token" };
  }
  if (PROXY_HEADERS.some((h) => headers[h])) {
    return { status: 403, error: "set RUNWAY_API_TOKEN before exposing the bridge" };
  }
  return null; // local dev: no token, direct request from this machine
}
