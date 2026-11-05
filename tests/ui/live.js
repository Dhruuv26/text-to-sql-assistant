// Live-mode click-through: the real page in jsdom talking over HTTP (with cookies) to a running server.
// Usage: node tests/ui/live.js http://127.0.0.1:PORT
const { JSDOM } = require("jsdom");
const assert = require("assert");
const base = process.argv[2].replace(/\/$/, "");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const jar = new Map();                    // the browser's cookie jar (HttpOnly cookies are invisible to page scripts)
const rawSetCookies = [];

async function open() {
  const html = await (await fetch(base + "/")).text();
  const dom = new JSDOM(html, { url: base + "/", runScripts: "outside-only", pretendToBeVisual: true });
  const w = dom.window;
  w.fetch = async (path, opts = {}) => {
    const headers = { ...(opts.headers || {}) };
    if (jar.size) headers.cookie = [...jar].map(([k, v]) => `${k}=${v}`).join("; ");
    let body = opts.body;
    if (body && typeof body === "object" && body.constructor && body.constructor.name === "File") {
      body = await new Promise((resolve, reject) => {
        const fr = new w.FileReader();
        fr.onload = () => resolve(Buffer.from(fr.result));
        fr.onerror = reject;
        fr.readAsArrayBuffer(body);
      });
    }
    const res = await fetch(new URL(path, base + "/"), { method: opts.method || "GET", headers, body });
    for (const c of res.headers.getSetCookie()) {
      rawSetCookies.push(c);
      const [pair, ...attrs] = c.split(";").map((x) => x.trim());
      const i = pair.indexOf("=");
      const [name, value] = [pair.slice(0, i), pair.slice(i + 1)];
      if (!value || attrs.some((a) => /^max-age=0$/i.test(a))) jar.delete(name); else jar.set(name, value);
    }
    return res;
  };
  w.Intl = Intl;
  w.navigator.clipboard = { writeText: async () => {} };
  w.HTMLElement.prototype.scrollIntoView = function () {};
  for (const f of ["app.js"]) w.eval(await (await fetch(`${base}/static/${f}`)).text());
  const d = w.document;
  const $ = (s) => d.querySelector(s), all = (s) => [...d.querySelectorAll(s)];
  const waitFor = async (cond, what, ms = 4000) => {
    const t0 = Date.now();
    while (Date.now() - t0 < ms) { try { if (cond()) return; } catch (_) { /* not ready */ } await sleep(25); }
    throw new Error("timed out waiting for: " + what);
  };
  await waitFor(() => all("#schema details").length > 0, "schema");
  return { w, d, $, all, waitFor, text: (el) => el.textContent };
}

function pickFile(w, d, name, content) {
  const input = d.querySelector("#file");
  Object.defineProperty(input, "files", { value: [new w.File([Buffer.from(content)], name, { type: "text/csv" })], configurable: true });
}
async function ask(p, q) {
  p.$("#answer").replaceChildren();
  p.$("#question").value = q;
  p.$("#ask-form").dispatchEvent(new p.w.Event("submit", { cancelable: true }));
  await p.waitFor(() => p.$("#answer").children.length > 0 && !p.$("#submit").disabled, "answer for: " + q);
}
async function switchTo(p, value) {
  const r = p.$(`input[name="source"][value="${value}"]`);
  r.checked = true;
  r.dispatchEvent(new p.w.Event("change", { bubbles: true }));
}

(async () => {
  const p = await open();
  const { w, d, $, all, text, waitFor } = p;

  // ---- sample mode is unchanged and the upload panel is offered
  assert.ok(!$("#source").hidden, "source chooser shown when the server supports uploads");
  assert.ok($("#upload-panel").hidden && !$("#examples-wrap").hidden);
  assert.strictEqual(all("#schema details").length, 11);
  assert.strictEqual($("#schema-h").textContent, "What is in the database");
  await ask(p, "How many artists are there?");
  assert.ok($("#answer table"), "sample question answered");

  // ---- switch to my file
  await switchTo(p, "upload");
  assert.ok(!$("#upload-panel").hidden && $("#examples-wrap").hidden);
  assert.strictEqual($("#schema-h").textContent, "What is in your file");
  assert.deepStrictEqual(all("#approach option").map((o) => o.value), ["", "plain", "profiled"]);
  assert.ok($("#remove-btn").hidden, "nothing to remove yet");
  const priv = text($("#privacy"));
  assert.ok(/30 minutes/.test(priv) && /2 hours/.test(priv) && /5 MB/.test(priv) && /confidential/.test(priv), "privacy note uses the server's real limits: " + priv);

  await ask(p, "Which region sold the most?");
  assert.ok(/Upload a file first/.test(text($("#answer .problem"))), "asking before uploading is explained");

  // ---- upload without choosing a file, then a bad file, then a good one
  $("#upload-btn").click();
  assert.ok(/Choose a file/.test(text($("#upload-status"))) && $("#upload-status").classList.contains("error"));

  pickFile(w, d, "empty.csv", "");
  $("#upload-btn").click();
  await waitFor(() => /empty/i.test(text($("#upload-status"))), "empty file rejected");
  assert.ok($("#upload-status").classList.contains("error") && $("#remove-btn").hidden && !$("#upload-btn").disabled);

  pickFile(w, d, "sales.csv", 'Region,Total Revenue ($),Company\nEast,"1,200",Acme\nWest,800,N/A\nEast,300,\nNorth,50,Zed\n');
  $("#upload-btn").click();
  await waitFor(() => /^Ready/.test(text($("#upload-status"))), "upload accepted");
  assert.ok(!$("#remove-btn").hidden);
  assert.ok(/^sales\s*4 rows$/.test(text($("#schema summary")).trim()), "table summary: " + text($("#schema summary")));
  const cols = all("#schema li").map((li) => text(li).replace(/\s+/g, " ").trim());
  assert.ok(cols.some((c) => /^total_revenue_usd integer/.test(c)), "normalised column name listed: " + cols.join("|"));
  assert.ok(cols.some((c) => /^company text, 2 missing/.test(c)), "NULL count shown: " + cols.join("|"));
  assert.strictEqual(all("#schema li").find((li) => /total_revenue_usd/.test(text(li))).title, "Original header: Total Revenue ($)");
  assert.ok(/minutes left/.test(text($("#privacy"))));
  assert.ok(rawSetCookies.some((c) => /^t2s_session=/.test(c) && /HttpOnly/i.test(c) && /SameSite=lax/i.test(c)), "cookie is HttpOnly + SameSite=Lax");
  assert.ok(!/t2s_session/.test(d.cookie), "page scripts cannot see the session cookie");

  // ---- ask about the file
  await ask(p, "Total revenue by region?");
  assert.strictEqual(text($("#answer h2")), "SQL");
  assert.deepStrictEqual(all("#answer tbody tr").map((tr) => [...tr.children].map(text)), [["East", "1,500"], ["North", "50"], ["West", "800"]]);
  const receipt = all(".receipt dd").map(text);
  assert.ok(receipt.includes("sales") && /profiled-retry/.test(receipt[receipt.length - 1]), "receipt names the table and approach: " + receipt.join("|"));

  // ---- a failed second upload leaves the session intact
  pickFile(w, d, "notes.exe", "a,b\n1,2\n");
  $("#upload-btn").click();
  await waitFor(() => /supported/i.test(text($("#upload-status"))), "unsupported type explained");
  assert.strictEqual(all("#schema details").length, 1, "existing table still listed");

  // ---- reload: a new page with the same cookie jar restores the session
  const q = await open();
  await q.waitFor(() => !q.$("#upload-panel").hidden, "reloaded page switches to my file");
  assert.ok(!q.$("#upload-panel").hidden && q.all("#schema details").length === 1 && /sales/.test(q.text(q.$("#schema summary"))), "reload restores the uploaded data");
  q.w.close();

  // ---- hostile headers and cells are shown as text and never become markup
  pickFile(w, d, "xss.csv", 'note,<img src=x onerror=alert(1)>\n"<script>alert(2)</script>",1\n"<b>bold</b>",2\n');
  $("#upload-btn").click();
  await waitFor(() => /^Ready/.test(text($("#upload-status"))), "hostile file accepted");
  await ask(p, "List notes");
  assert.ok($("#answer table"), "result table rendered");
  assert.strictEqual(all("#answer img, #answer script, #answer b, #schema img, #schema script, #upload-warnings img").length, 0, "no injected elements");
  assert.deepStrictEqual(all("#answer tbody td").map(text), ["<script>alert(2)</script>", "<b>bold</b>"], "cell values are literal text");

  // ---- remove my data
  $("#remove-btn").click();
  await waitFor(() => /removed/i.test(text($("#upload-status"))), "data removed");
  assert.ok($("#remove-btn").hidden && all("#schema details").length === 0);
  assert.strictEqual(all("#answer *").length, 0);
  const st = await (await fetch(base + "/api/session", { headers: { cookie: [...jar].map(([k, v]) => `${k}=${v}`).join("; ") } })).json();
  assert.strictEqual(st.active, false, "server forgot the session");
  assert.strictEqual(jar.size, 0, "cookie cleared");
  await ask(p, "Total revenue by region?");
  assert.ok(/Upload a file first/.test(text($("#answer .problem"))));

  // ---- back to the sample database
  await switchTo(p, "sample");
  assert.ok($("#upload-panel").hidden && !$("#examples-wrap").hidden && all("#schema details").length === 11);
  assert.deepStrictEqual(all("#approach option").map((o) => o.value), ["", "zero_shot", "shots_only", "fewshot", "docs"]);
  console.log("ui live ok");
  process.exit(0);
})().catch((e) => { console.error(e); process.exit(1); });
