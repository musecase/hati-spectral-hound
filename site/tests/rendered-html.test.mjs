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
  assert.match(html, /youtube-nocookie\.com\/embed\/1FV-zFQfFqc/);
  assert.match(html, /WATCH ON YOUTUBE/);
  assert.match(html, /Luna screens frames 2 and 4/);
  assert.doesNotMatch(html, /VIDEO IN PRODUCTION|premiere slot reserved/);
  assert.doesNotMatch(html, /FIELD TESTED|LIVE TESTED|WATER TESTED|LIVE VERIFIED/);
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
  assert.match(experience, /youtube\.com\/watch\?v=1FV-zFQfFqc/);
  assert.match(experience, /No live raccoon encounter yet/);
  assert.doesNotMatch(experience, /No scent has been loaded|replace this site&apos;s video placeholder/);
  assert.doesNotMatch(experience, /THE FIVE-FRAME TEST|HUMAN IN THE LEARNING LOOP|CURRENT FIELD NOTES/);
  assert.match(page, /images: \[\{ url: "\/og\.png"/);
  assert.match(layout, /hati-spectral-hound\.amarygma\.chatgpt\.site/);
});
