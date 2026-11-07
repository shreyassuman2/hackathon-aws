import assert from "node:assert/strict";
import { test } from "node:test";

import { authorize, sameSecret } from "../src/auth.js";

const TOKEN = "test-" + "x".repeat(24); // obviously fake, so the secret scanner doesn't flag it

test("with a token set, /send needs exactly that token", () => {
  assert.equal(authorize({ "x-runway-token": TOKEN }, TOKEN), null);
  assert.equal(authorize({}, TOKEN).status, 401);
  assert.equal(authorize({ "x-runway-token": "wrong" }, TOKEN).status, 401);
  assert.equal(authorize({ "x-runway-token": TOKEN + "x" }, TOKEN).status, 401);
  // A correct token through a tunnel is fine: that's how the deployed API reaches the bridge.
  assert.equal(authorize({ "x-runway-token": TOKEN, "cf-connecting-ip": "1.2.3.4" }, TOKEN), null);
});

test("without a token, only direct local requests are allowed", () => {
  assert.equal(authorize({}, ""), null);
  for (const h of ["x-forwarded-for", "cf-connecting-ip", "forwarded", "x-real-ip"]) {
    assert.equal(authorize({ [h]: "1.2.3.4" }, "").status, 403, h);
  }
});

test("sameSecret never matches an empty secret", () => {
  assert.equal(sameSecret("", ""), false);
  assert.equal(sameSecret(undefined, ""), false);
  assert.equal(sameSecret("abc", "abc"), true);
});
