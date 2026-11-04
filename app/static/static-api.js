// Replay mode: answers /api/* calls from data.json instead of a server (used by the GitHub Pages build).
(function (root) {
  "use strict";
  const norm = (q) => String(q).toLowerCase().split(/\s+/).filter(Boolean).join(" ");
  const reply = (data, status = 200) => ({ ok: status >= 200 && status < 300, status, data, retry: null });

  function makeStaticApi(data) {
    const all = [...data.examples, ...(data.blocked || [])];
    const byQuestion = new Map(all.map((r) => [norm(r.question), r]));
    return async function api(path, opts) {
      if (path === "/api/examples") return reply(data.examples.map((r) => r.question));
      if (path === "/api/blocked") return reply((data.blocked || []).map((r) => r.question));
      if (path === "/api/schema") return reply(data.schema);
      if (path === "/api/health") return reply({ status: "ok", static: true, llm_ready: false, model: data.model, examples_precomputed: data.examples.length });
      if (path === "/api/ask") {
        let question = "";
        try { question = JSON.parse((opts && opts.body) || "{}").question || ""; } catch (_) { /* malformed body */ }
        const hit = byQuestion.get(norm(question));
        if (hit) return reply(hit);
        return reply({ detail: "This page replays saved answers only, so it cannot answer new questions. Pick one of the examples, or run the app locally to ask your own (see the README)." }, 404);
      }
      return reply({ detail: "Not found" }, 404);
    };
  }
  const api = { makeStaticApi, norm };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.StaticApi = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
