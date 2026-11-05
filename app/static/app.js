(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const el = (tag, cls, text) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  };
  const fmt = new Intl.NumberFormat("en-US");

  const HINTS = {
    not_select: "Only read-only questions run here, so a statement that changes data was blocked. Rephrase as a question about the data.",
    multiple_statements: "Only a single SELECT statement is allowed. Ask one question at a time.",
    forbidden_table: "The SQL referred to a table that is not in this database. Check the table list on the right and rephrase.",
    forbidden_function: "The SQL used a function that is not allowed. Rephrase the question.",
    parse_error: "The model wrote SQL that could not be parsed. Try rephrasing, or ask a simpler version of the question.",
    db_error: "The database rejected the SQL the model wrote. Try rephrasing, and name tables or columns the way the list on the right does.",
    timeout: "The query ran longer than the time limit and was stopped. Ask for a narrower result.",
    empty: "The model returned no SQL. Try rephrasing the question.",
    too_complex: "The SQL the model wrote was too deeply nested to check safely. Try a simpler question.",
    read_only: "Nothing was run. This assistant only reads data.",
  };
  const WARNINGS = {
    copied_example: ["This SQL is one of the stored examples the model was shown, not a query written for your question.",
      "It probably does not answer what you asked. Rephrase the question, or ask about the tables listed on the right."],
    no_data_source: ["This query does not read any table, so the text it shows was written by the model, not taken from the database.",
      "Treat it as unverified, and especially do not read it as confirmation that anything was changed."],
  };
  const BLOCKED = new Set(["read_only", "not_select", "multiple_statements", "forbidden_table", "forbidden_function", "parse_error", "empty", "too_long", "too_complex", "forbidden_statement"]);

  let busy = false;

  const STATIC = document.documentElement.dataset.mode === "static";
  let staticApi = null;

  async function api(path, opts) {
    if (STATIC) {                                   // GitHub Pages replay: no server, answers come from data.json
      if (!staticApi) staticApi = window.StaticApi.makeStaticApi(await (await fetch("data.json")).json());
      return staticApi(path, opts);
    }
    const r = await fetch(path, opts);
    let data = null;
    try { data = await r.json(); } catch (_) { /* non-JSON error body */ }
    return { ok: r.ok, status: r.status, data, retry: r.headers.get("Retry-After") };
  }

  function receiptRow(label, value, cls) {
    const row = el("div");
    row.append(el("dt", "", label), el("span", "lead"), el("dd", cls || "", value));
    row.querySelector(".lead").setAttribute("aria-hidden", "true");
    return row;
  }

  function renderAnswer(d) {
    const box = $("answer");
    box.replaceChildren();

    (d.warnings || []).forEach((code) => {
      const text = WARNINGS[code];
      if (!text) return;
      const w = el("div", "problem warning");
      text.forEach((line) => w.append(el("p", "", line)));
      box.append(w);
    });

    if (d.sql) {
      const blk = el("div", "block");
      const head = el("div", "block-head");
      head.append(el("h2", "", !d.ok && BLOCKED.has(d.code) ? "SQL the model wrote (not run)" : "SQL"));
      const copy = el("button", "copy", "Copy SQL");
      copy.type = "button";
      copy.addEventListener("click", async () => {
        try { await navigator.clipboard.writeText(d.sql); copy.textContent = "Copied"; }
        catch (_) { copy.textContent = "Copy failed"; }
        setTimeout(() => { copy.textContent = "Copy SQL"; }, 1500);
      });
      head.append(copy);
      const pre = el("pre");
      pre.append(el("code", "", d.sql));
      blk.append(head, pre);
      box.append(blk);
    }

    const rec = el("div", "block");
    rec.append(el("h2", "", "What the checks did"));
    const dl = el("dl", "receipt");
    const blocked = !d.ok && BLOCKED.has(d.code);
    dl.append(receiptRow("Statement", blocked ? "Blocked before running" : "One SELECT, read-only connection", blocked ? "blocked" : "passed"));
    dl.append(receiptRow("Tables", d.tables && d.tables.length ? d.tables.join(", ") : "none"));
    if (!blocked) {
      const rows = `${fmt.format(d.row_count)} returned, limit ${fmt.format(d.row_limit)}` + (d.truncated ? " (more rows were cut off)" : "");
      dl.append(receiptRow("Rows", rows));
    }
    const timing = d.source === "policy" ? `${d.total_ms} ms` : d.source === "recorded" ? "not run" : d.source === "saved" ? `database ${d.exec_ms} ms` : `model ${fmt.format(d.llm_ms)} ms, database ${d.exec_ms} ms`;
    dl.append(receiptRow("Time", timing));
    let from = d.source === "policy" ? "Not sent to the model (read-only policy)"
      : d.source === "recorded" ? `${d.model}, recorded in the red-team run with the wording check switched off`
      : d.source === "saved" ? "Saved answer, verified correct in evaluation" : `${d.model}, ${d.approach.replace("_", "-")}`;
    if (d.source === "model" && d.attempts > 1) from += `, ${d.attempts} attempts`;
    dl.append(receiptRow("Written by", from));
    rec.append(dl);
    box.append(rec);

    const res = el("div", "block");
    if (!d.ok) {
      res.append(el("h2", "", d.code === "read_only" ? "Nothing was run" : "No result"));
      const p = el("div", "problem");
      p.append(el("p", "", d.code === "read_only" ? d.error : HINTS[d.code] || "Something went wrong running that query. Try rephrasing the question."));
      if (d.error && d.code !== "read_only") p.append(el("p", "detail", d.error));
      res.append(p);
    } else if (d.row_count === 0) {
      res.append(el("h2", "", "Result"));
      res.append(el("p", "note", "The query ran and returned no rows. Check names and values in the question, or look at the SQL filters above."));
    } else {
      res.append(el("h2", "", `Result: ${fmt.format(d.row_count)} ${d.row_count === 1 ? "row" : "rows"}`));
      const wrap = el("div", "scroll");
      wrap.setAttribute("role", "region");
      wrap.setAttribute("aria-label", "Query result");
      wrap.tabIndex = 0;
      const table = el("table");
      const numeric = d.columns.map((_, i) => d.rows.every((r) => r[i] === null || typeof r[i] === "number"));
      // identifiers, years and codes must not get thousands separators (2021, not 2,021)
      const plain = d.columns.map((c) => /(id|year|yr|zip|postal|phone|fax|code)$/i.test(c.trim()));
      const thead = el("thead");
      const hr = el("tr");
      d.columns.forEach((c, i) => hr.append(Object.assign(el("th", numeric[i] ? "num" : "", c), { scope: "col" })));
      thead.append(hr);
      const tbody = el("tbody");
      d.rows.forEach((r) => {
        const tr = el("tr");
        r.forEach((v, i) => tr.append(el("td", numeric[i] ? "num" : "", v === null ? "null" : typeof v === "number" && !plain[i] ? fmt.format(v) : String(v))));
        tbody.append(tr);
      });
      table.append(thead, tbody);
      wrap.append(table);
      res.append(wrap);
      if (d.truncated) res.append(el("p", "note", `Showing the first ${fmt.format(d.row_limit)} rows.`));
    }
    box.append(res);
    box.scrollIntoView({ block: "nearest" });
  }

  function renderProblem(message) {
    const box = $("answer");
    box.replaceChildren();
    const p = el("div", "problem");
    p.append(el("p", "", message));
    box.append(p);
  }

  // ---- uploads: live mode only (the replay site hides this panel and never calls these routes)
  let source = "sample";                                   // "sample" | "upload"
  let session = null;                                      // last active /api/session payload
  let sessionInfo = { limits: null, ttl_s: 1800, max_age_s: 7200 };
  let sampleSchema = [];
  let uploading = false;
  const sampleApproaches = [...$("approach").options].map((o) => [o.value, o.textContent]);
  const SAMPLE_PLACEHOLDER = $("question").placeholder;
  const SAMPLE_DESC = $("schema-desc").textContent;
  const UPLOAD_APPROACHES = [["", "Default (recommended)"], ["plain", "Column names and types only"],
    ["profiled", "Adds missing-value counts, ranges and categories"]];

  function renderSidebar() {
    const root = $("schema");
    root.replaceChildren();
    if (source === "upload") {
      $("schema-h").textContent = "What is in your file";
      if (!session) {
        $("schema-desc").textContent = "Upload a file and its tables will be listed here.";
        return;
      }
      $("schema-desc").textContent = "Column names were tidied so they work in SQL (for example \"Total Revenue ($)\" becomes total_revenue_usd). " +
        "Empty cells, N/A and similar become missing values. Open a table to see its columns.";
      session.tables.forEach((t) => {
        const d = el("details");
        d.open = session.tables.length === 1;
        const s = el("summary");
        s.append(el("span", "", t.name), el("span", "count", `${fmt.format(t.rows)} rows`));
        const ul = el("ul");
        t.columns.forEach((c) => {
          const li = el("li", "", c.name);
          li.append(el("span", "", " " + c.type.toLowerCase() + (c.nulls ? `, ${fmt.format(c.nulls)} missing` : "")));
          if (c.label && c.label !== c.name) li.title = "Original header: " + c.label;
          ul.append(li);
        });
        d.append(s, ul);
        root.append(d);
      });
      return;
    }
    $("schema-h").textContent = "What is in the database";
    $("schema-desc").textContent = SAMPLE_DESC;
    sampleSchema.forEach((t) => {
      const d = el("details");
      const s = el("summary");
      s.append(el("span", "", t.table), el("span", "count", `${fmt.format(t.rows)} rows`));
      const ul = el("ul");
      t.columns.forEach((c) => {
        const li = el("li", "", c.name + (c.pk ? " (key)" : ""));
        li.append(el("span", "", " " + c.type.toLowerCase()));
        ul.append(li);
      });
      t.foreign_keys.forEach((f) => ul.append(el("li", "", `links: ${f}`)));
      d.append(s, ul);
      root.append(d);
    });
  }

  function renderPrivacy() {
    const lim = sessionInfo.limits || {};
    const mins = Math.round(sessionInfo.ttl_s / 60);
    const hours = Math.round((sessionInfo.max_age_s / 3600) * 10) / 10;
    let t = "Your file is sent to this server and read by the language model running on the same machine. It is kept in a private session, " +
      `deleted after ${mins} minutes without use (never kept longer than ${hours} ${hours === 1 ? "hour" : "hours"}), and deleted at once when you press Remove my data.`;
    if (lim.max_bytes) t += ` Limits: ${Math.round(lim.max_bytes / 1e6)} MB, ${fmt.format(lim.max_rows)} rows, ${lim.max_cols} columns.`;
    t += " Do not upload anything confidential.";
    if (session) t += ` About ${Math.max(1, Math.round(session.seconds_left / 60))} minutes left in this session.`;
    $("privacy").textContent = t;
  }

  function applySession(d) {
    if (d && typeof d.ttl_s === "number") sessionInfo = { limits: d.limits || sessionInfo.limits, ttl_s: d.ttl_s, max_age_s: d.max_age_s || sessionInfo.max_age_s };
    session = d && d.active ? d : null;
    $("remove-btn").hidden = !session;
    renderPrivacy();
    renderSidebar();
  }

  async function refreshSession() {
    const r = await api("/api/session");
    if (r.ok) applySession(r.data);
    return r;
  }

  function setSource(next) {
    source = next;
    document.querySelectorAll('input[name="source"]').forEach((r) => { r.checked = r.value === next; });
    $("upload-panel").hidden = next !== "upload";
    $("examples-wrap").hidden = next === "upload";
    $("question").placeholder = next === "upload" ? "Which category has the highest total?" : SAMPLE_PLACEHOLDER;
    const sel = $("approach");
    sel.replaceChildren();
    (next === "upload" ? UPLOAD_APPROACHES : sampleApproaches).forEach(([v, t]) => {
      const o = el("option", "", t);
      o.value = v;
      sel.append(o);
    });
    $("answer").replaceChildren();
    renderSidebar();
  }

  function uploadStatus(msg, isError) {
    const s = $("upload-status");
    s.textContent = msg;
    s.classList.toggle("error", !!isError);
  }

  async function upload() {
    if (uploading) return;
    const file = $("file").files && $("file").files[0];
    if (!file) return uploadStatus("Choose a file first.", true);
    const max = sessionInfo.limits && sessionInfo.limits.max_bytes;
    if (max && file.size > max) return uploadStatus(`That file is ${(file.size / 1e6).toFixed(1)} MB; the limit is ${Math.round(max / 1e6)} MB.`, true);
    uploading = true;
    $("upload-btn").disabled = true;
    uploadStatus("Uploading and reading the file.");
    try {
      const r = await api("/api/upload?filename=" + encodeURIComponent(file.name), { method: "POST", body: file });
      if (r.ok) {
        applySession(r.data);
        $("upload-warnings").replaceChildren(...(r.data.warnings || []).map((w) => el("li", "", w)));
        $("file").value = "";
        uploadStatus("Ready. Ask a question about your data.");
      } else if (r.status === 429) {
        uploadStatus(((r.data && r.data.detail) || "Too many uploads.") + (r.retry ? ` Try again in ${r.retry} seconds.` : ""), true);
      } else {
        uploadStatus((r.data && r.data.detail) || "The file could not be uploaded.", true);
      }
    } catch (_) {
      uploadStatus("Could not reach the server. Check your connection and try again.", true);
    } finally {
      uploading = false;
      $("upload-btn").disabled = false;
    }
  }

  async function removeData() {
    const r = await api("/api/session", { method: "DELETE" });
    if (r.ok) {
      applySession({ active: false });
      $("upload-warnings").replaceChildren();
      $("answer").replaceChildren();
      uploadStatus("Your data was removed.");
    } else {
      uploadStatus("Could not remove your data. It is deleted automatically when the session expires.", true);
    }
  }

  async function ask(question) {
    if (busy || question.trim().length < 3) return;
    const mine = source === "upload";
    if (mine && !session) { renderProblem("Upload a file first, then ask a question about it."); return; }
    busy = true;
    $("submit").disabled = true;
    $("submit").textContent = "Asking";
    $("status").textContent = "Writing the SQL. The first question after a quiet period can take a few seconds.";
    const approach = $("approach").value || null;
    try {
      const r = await api(mine ? "/api/session/ask" : "/api/ask", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question, approach }) });
      if (r.ok) {
        renderAnswer(r.data);
        if (mine) refreshSession().catch(() => {});
      } else if (mine && (r.status === 404 || r.status === 410)) {
        renderProblem("Your uploaded data is gone (it expired or was removed). Upload the file again.");
        applySession({ active: false });
      } else if (r.status === 429) renderProblem(`You have reached the request limit. Try again in ${r.retry || "a few"} seconds.`);
      else if (r.status === 422) renderProblem("That question could not be read. Use between 3 and 400 characters.");
      else renderProblem((r.data && r.data.detail) || "The service could not answer. Try again in a moment.");
    } catch (_) {
      renderProblem("Could not reach the server. Check your connection and try again.");
    } finally {
      busy = false;
      $("submit").disabled = false;
      $("submit").textContent = "Ask";
      $("status").textContent = "";
    }
  }

  $("ask-form").addEventListener("submit", (e) => { e.preventDefault(); ask($("question").value); });
  $("question").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); ask($("question").value); }
  });

  async function init() {
    const [ex, sc, hl] = await Promise.all([api("/api/examples"), api("/api/schema"), api("/api/health")]);
    if (ex.ok) {
      const ul = $("examples");
      ex.data.forEach((q) => {
        const li = el("li");
        const b = el("button", "", q);
        b.type = "button";
        b.addEventListener("click", () => { $("question").value = q; ask(q); });
        li.append(b);
        ul.append(li);
      });
    }
    if (sc.ok) {
      sampleSchema = sc.data;
      renderSidebar();
    }
    if (!STATIC && hl.ok && hl.data && hl.data.uploads) {
      $("source").hidden = false;
      document.querySelectorAll('input[name="source"]').forEach((r) => r.addEventListener("change", () => { if (r.checked) setSource(r.value); }));
      $("upload-btn").addEventListener("click", upload);
      $("remove-btn").addEventListener("click", removeData);
      renderPrivacy();
      await refreshSession();                          // a reload keeps working while the session is alive
      if (session) setSource("upload");
    }
    if (STATIC) {
      const bl = await api("/api/blocked");
      if (bl.ok && bl.data.length) {
        const ul = $("blocked");
        bl.data.forEach((q) => {
          const li = el("li");
          const b = el("button", "", q);
          b.type = "button";
          b.addEventListener("click", () => { $("question").value = q; ask(q); });
          li.append(b);
          ul.append(li);
        });
        $("blocked-wrap").hidden = false;
      }
      const b = $("banner");
      b.hidden = false;
      b.textContent = "This page is a replay. The SQL was written by a language model in real runs and the rows come from the real database, but nothing is generated here. To ask your own question, run the app locally (see the README).";
    } else if (hl.ok && hl.data && !hl.data.llm_ready) {
      const b = $("banner");
      b.hidden = false;
      b.textContent = hl.data.examples_precomputed
        ? "The language model is offline right now. The example questions still work; new questions will not."
        : "The language model is offline right now, so new questions cannot be answered.";
    }
  }
  init();
})();
