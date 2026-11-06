"""Download the benchmark CSVs from the original repositories at pinned commits and verify SHA-256.

  python -m eval.csvbench.fetch            (files go to cache/csvbench/raw/, which is git-ignored)

No scraping and no API keys: plain GETs of raw.githubusercontent.com URLs that name an exact commit.
"""
from __future__ import annotations

import hashlib
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "cache" / "csvbench"
MANIFEST = Path(__file__).with_name("manifest.json")


class FetchError(RuntimeError):
    pass


def load_manifest(path: Path = MANIFEST) -> dict:
    return json.loads(Path(path).read_text())


def raw_path(entry: dict, cache: Path = CACHE) -> Path:
    return Path(cache) / "raw" / entry["file"]


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def is_verified(entry: dict, cache: Path = CACHE) -> bool:
    p = raw_path(entry, cache)
    return p.exists() and sha256_of(p.read_bytes()) == entry["sha256"]


def fetch_one(entry: dict, cache: Path = CACHE, timeout: float = 60) -> str:
    p = raw_path(entry, cache)
    if is_verified(entry, cache):
        return "cached"
    req = urllib.request.Request(entry["url"], headers={"User-Agent": "text2sql-csvbench"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
    got = sha256_of(data)
    if got != entry["sha256"]:
        raise FetchError(f"{entry['file']}: SHA-256 mismatch (expected {entry['sha256'][:12]}..., got {got[:12]}...). "
                         "The file at that commit should never change; refusing to use it.")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return "downloaded"


def fetch_all(manifest: dict | None = None, cache: Path = CACHE) -> dict[str, str]:
    manifest = manifest or load_manifest()
    return {e["id"]: fetch_one(e, cache) for e in manifest["datasets"]}


def main() -> int:
    try:
        for k, v in fetch_all().items():
            print(f"{k:18} {v}")
    except (FetchError, OSError) as e:
        print("ERROR:", e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
