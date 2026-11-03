"""python -m app.cli "How many artists are there?" [--model qwen2.5-coder:7b]"""
import argparse

from .llm import CachedLLM, OllamaClient
from .pipeline import Text2SQL


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("question")
    ap.add_argument("--model", default="qwen2.5-coder:7b")
    ap.add_argument("--approach", default="zero_shot", choices=["zero_shot", "fewshot", "self_correct", "docs", "shots_only", "vote"])
    ap.add_argument("--no-cache", action="store_true")
    a = ap.parse_args()
    llm = OllamaClient(a.model)
    llm = llm if a.no_cache else CachedLLM(llm)
    sampler = lambda i: (lambda c: c if a.no_cache else CachedLLM(c))(OllamaClient(a.model, temperature=0.6, seed=i))
    out = Text2SQL(llm, sampler_factory=sampler).ask(a.question, a.approach)
    print(f"SQL: {out.sql}\n")
    r = out.result
    if not r.ok:
        print(f"[{r.code}] {r.error}")
        return
    print(" | ".join(r.columns))
    for row in r.rows[:20]:
        print(" | ".join(map(str, row)))
    print(f"\n{len(r.rows)} rows{' (truncated)' if r.truncated else ''}, llm {out.llm_latency_ms:.0f} ms"
          f"{' (cached)' if out.cached else ''}")


if __name__ == "__main__":
    main()
