// Loads the generated static site in jsdom and clicks through it. Usage: node tests/ui/replay.js <site-dir>
const { JSDOM } = require("jsdom");
const assert = require("assert");
const fs = require("fs");
const dir = process.argv[2].replace(/\/?$/, "/");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  const dom = new JSDOM(fs.readFileSync(dir + "index.html", "utf8"), { url: "https://example.github.io/repo/", runScripts: "outside-only", pretendToBeVisual: true });
  const w = dom.window;
  w.fetch = async (p) => ({ ok: true, status: 200, headers: { get: () => null }, json: async () => JSON.parse(fs.readFileSync(dir + p, "utf8")) });
  w.Intl = Intl;
  w.navigator.clipboard = { writeText: async () => {} };
  w.HTMLElement.prototype.scrollIntoView = function () {};
  for (const f of ["static-api.js", "app.js"]) w.eval(fs.readFileSync(dir + f, "utf8"));
  await sleep(300);
  const d = w.document, $ = (s) => d.querySelector(s), all = (s) => [...d.querySelectorAll(s)];
  const text = (el) => el.textContent;
  const click = async (el) => { el.click(); await sleep(250); };

  assert.strictEqual(d.documentElement.dataset.mode, "static");
  assert.ok(!$("#banner").hidden && /replay/i.test(text($("#banner"))), "replay banner");
  assert.ok(all("#examples button").length >= 1 && all("#blocked button").length >= 2 && !$("#blocked-wrap").hidden, "chips");
  assert.strictEqual(all("#schema details").length, 11, "schema");

  await click($("#examples button"));
  assert.strictEqual(text($("#answer h2")), "SQL");
  assert.ok($("#answer pre code") && $("#answer table") && all("#answer tbody tr").length >= 1, "example renders SQL and table");
  assert.deepStrictEqual(all(".receipt dt").map(text), ["Statement", "Tables", "Rows", "Time", "Written by"]);
  assert.ok(/Saved answer/.test(text(all(".receipt dd").pop())));

  await click(all("#blocked button").find((b) => /Delete all/.test(text(b))));
  assert.strictEqual(text($("#answer h2")), "SQL the model wrote (not run)");
  assert.ok(/DELETE/.test(text($("#answer pre code"))) && $("#answer .problem"), "blocked statement shown with a problem box");
  assert.strictEqual(text($(".receipt dd")), "Blocked before running");
  assert.ok(/recorded in the red-team run/.test(text(all(".receipt dd").pop())));
  assert.ok(!$("#answer table"), "no result table for a blocked query");

  await click(all("#blocked button").find((b) => /truncate/i.test(text(b))));
  assert.ok(all("#answer h2").map(text).includes("Nothing was run") && !$("#answer pre"), "policy refusal has no SQL");

  $("#question").value = "Something nobody saved";
  $("#ask-form").dispatchEvent(new w.Event("submit", { cancelable: true }));
  await sleep(250);
  assert.ok(/replays saved answers only/.test(text($("#answer .problem p"))), "unknown question explained");
  assert.strictEqual($("#submit").disabled, false);
  assert.strictEqual(text($("#submit")), "Ask");
  console.log("ui replay ok");
})().catch((e) => { console.error(e); process.exit(1); });
