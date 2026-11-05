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

  async function ask(question) {
    if (busy || question.trim().length < 3) return;
    busy = true;
    $("submit").disabled = true;
    $("submit").textContent = "Asking";
    $("status").textContent = "Writing the SQL. The first question after a quiet period can take a few seconds.";
    const approach = $("approach").value || null;
    try {
      const r = await api("/api/ask", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question, approach }) });
      if (r.ok) renderAnswer(r.data);
      else if (r.status === 429) renderProblem(`You have reached the request limit. Try again in ${r.retry || "a few"} seconds.`);
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
      const root = $("schema");
      sc.data.forEach((t) => {
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
