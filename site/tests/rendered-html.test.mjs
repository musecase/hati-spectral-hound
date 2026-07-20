import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    new Request("http://localhost/", { headers: { accept: "text/html" } }),
    { ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) } },
    { waitUntil() {}, passThroughOnException() {} },
  );
}

test("server-renders the complete HATI judge experience", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /<title>HATI — Spectral Hound \| HATI<\/title>/i);
  assert.match(html, /An AI farm bouncer/);
  assert.match(html, /Run the evidence/);
  assert.match(html, /human veto clear/i);
  assert.match(html, /CONTROLLED EVALUATION/);
  assert.match(html, /MISS CAUGHT · RULE NARROWED/);
  assert.match(html, /YouTube premiere slot reserved/);
  assert.match(html, /No hand-waving/);
  assert.match(html, /property="og:image"/);
  assert.doesNotMatch(html, /codex-preview|Your site is taking shape/);
});

test("keeps verified claims and public links in source", async () => {
  const [experience, page, layout] = await Promise.all([
    readFile(new URL("../app/HatiExperience.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/layout.tsx", import.meta.url), "utf8"),
  ]);

  assert.match(experience, /feedback-derived|zero regressions/i);
  assert.match(experience, /HUMAN_VETO/);
  assert.match(experience, /github\.com\/musecase\/hati-spectral-hound/);
  assert.match(experience, /No live raccoon encounter yet/);
  assert.match(experience, /LIVE VERIFIED/);
  assert.match(page, /images: \[\{ url: "\/og\.png"/);
  assert.match(layout, /hati-spectral-hound\.amarygma\.chatgpt\.site/);
});
