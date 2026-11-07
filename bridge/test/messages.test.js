import assert from "node:assert/strict";
import { test } from "node:test";

import { asString, normalize, sendScript, textFromAttributedBody } from "../src/messages.js";

test("normalize matches the backend's phone format", () => {
  assert.equal(normalize("(415) 555-0100"), "+14155550100");
  assert.equal(normalize("+1 415 555 0100"), "+14155550100");
  assert.equal(normalize("Founder@Acme.ai"), "founder@acme.ai");
  assert.equal(normalize(""), "");
});

test("AppleScript strings are escaped", () => {
  assert.equal(asString('say "hi" \\ bye'), '"say \\"hi\\" \\\\ bye"');
  assert.ok(sendScript("+14155550100", 'a "quote"').includes('send "a \\"quote\\""'));
});

test("text is recovered from attributedBody", () => {
  const text = "Y";
  const buf = Buffer.concat([
    Buffer.from("streamtyped\x81\xe8\x03\x84\x01@\x84\x84\x84\x12NSAttributedString\x00\x84\x84\x08NSObject\x00\x85\x92\x84\x84\x84\x08NSString\x01\x94\x84\x01+", "latin1"),
    Buffer.from([text.length]),
    Buffer.from(text),
    Buffer.from("\x86\x84\x02iI", "latin1"),
  ]);
  assert.equal(textFromAttributedBody(buf), "Y");
  assert.equal(textFromAttributedBody(null), null);
});
