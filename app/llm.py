"""LLM providers behind one interface, plus a deterministic on-disk cache.

Providers: OllamaClient (local, default), OpenAICompatClient (any OpenAI-style endpoint: Gemini, Groq, ...),
FakeLLM (tests). CachedLLM wraps any provider so eval reruns are free and reproducible.
"""
from __future__ import annotations

import hashlib
import json
import time
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Protocol

DEFAULT_CACHE_DIR = Path(__file__).resolve().parent.parent / "cache"


@dataclass
class LLMResponse:
    text: str
    latency_ms: float          # latency of the ORIGINAL model call (kept on cache hits, so eval timings stay honest)
    cached: bool = False


class LLMClient(Protocol):
    name: str                  # identifies provider+model+params; part of the cache key
    def generate(self, prompt: str, system: str | None = None) -> LLMResponse: ...


def _post_json(url: str, payload: dict, headers: dict | None = None, timeout: float = 180) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json", **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


class OllamaClient:
    def __init__(self, model: str = "qwen2.5-coder:7b", host: str = "http://localhost:11434",
                 temperature: float = 0.0, num_ctx: int = 8192, seed: int = 0, max_tokens: int = 512, timeout: float = 180):
        self.model, self.host, self.timeout = model, host.rstrip("/"), timeout
        self.options = {"temperature": temperature, "num_ctx": num_ctx, "seed": seed, "num_predict": max_tokens}
        self.name = f"ollama:{model}:{json.dumps(self.options, sort_keys=True)}"

    def generate(self, prompt: str, system: str | None = None) -> LLMResponse:
        payload = {"model": self.model, "prompt": prompt, "stream": False, "options": self.options,
                   "keep_alive": "30m"}   # keep weights in VRAM between calls (avoids cold-start per question)
        if system:
            payload["system"] = system
        t0 = time.perf_counter()
        try:
            data = _post_json(f"{self.host}/api/generate", payload, timeout=self.timeout)
        except OSError as e:
            raise RuntimeError(f"Cannot reach Ollama at {self.host} ({e}). Is `ollama serve` running "
                               f"and `ollama pull {self.model}` done?") from e
        return LLMResponse(data["response"], (time.perf_counter() - t0) * 1000)


    def ping(self, timeout: float = 1.5) -> bool:
        """True if the Ollama server answers (used by the API health check)."""
        try:
            with urllib.request.urlopen(f"{self.host}/api/tags", timeout=timeout):
                return True
        except OSError:
            return False


class OpenAICompatClient:
    """Works with any /chat/completions endpoint (Gemini's OpenAI-compat URL, Groq, vLLM, LM Studio...)."""
    def __init__(self, base_url: str, model: str, api_key: str = "", temperature: float = 0.0, max_tokens: int = 512):
        self.base_url, self.model, self.api_key = base_url.rstrip("/"), model, api_key
        self.params = {"temperature": temperature, "max_tokens": max_tokens}
        self.name = f"openai:{base_url}:{model}:{json.dumps(self.params, sort_keys=True)}"

    def generate(self, prompt: str, system: str | None = None) -> LLMResponse:
        msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
        t0 = time.perf_counter()
        data = _post_json(f"{self.base_url}/chat/completions", {"model": self.model, "messages": msgs, **self.params},
                          {"Authorization": f"Bearer {self.api_key}"})
        return LLMResponse(data["choices"][0]["message"]["content"], (time.perf_counter() - t0) * 1000)


class FakeLLM:
    """Deterministic stub for tests: responder(prompt) -> text."""
    def __init__(self, responder: Callable[[str], str] | str, name: str = "fake"):
        self.responder = responder if callable(responder) else (lambda _p, _r=responder: _r)
        self.name = name
        self.calls = 0

    def generate(self, prompt: str, system: str | None = None) -> LLMResponse:
        self.calls += 1
        return LLMResponse(self.responder(prompt), 1.0)


class CachedLLM:
    def __init__(self, inner: LLMClient, cache_dir: str | Path = DEFAULT_CACHE_DIR):
        self.inner, self.dir = inner, Path(cache_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.name = inner.name
        self.hits = self.misses = 0

    def _key(self, prompt: str, system: str | None) -> str:
        blob = json.dumps({"m": self.inner.name, "s": system, "p": prompt}, sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()

    def generate(self, prompt: str, system: str | None = None) -> LLMResponse:
        path = self.dir / f"{self._key(prompt, system)}.json"
        if path.exists():
            self.hits += 1
            d = json.loads(path.read_text())
            return LLMResponse(d["text"], d["latency_ms"], cached=True)
        self.misses += 1
        resp = self.inner.generate(prompt, system)
        path.write_text(json.dumps(asdict(resp)))
        return resp
