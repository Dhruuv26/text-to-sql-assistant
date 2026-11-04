# Publishing and running it

## What "public demo" can honestly mean here

The expensive part is the language model; the database is a 1 MB SQLite file. **No free host can run the model.** Hugging Face moved Docker and Gradio Spaces on its free CPU tier behind a paid plan in July 2026 (only Static Spaces remain free), and other free web hosts have far too little memory for even a 3B model.

So there are three ways to run this project, and the README says which one you are looking at:

| Mode | Cost | New questions? | How |
|---|---|---|---|
| **Replay site** (GitHub Pages) | free, no card, no keys | no: saved answers only | section 1 |
| **Live, on your own machine** | free | yes (~3 s on an RTX 4060, 7B) | section 2 |
| **Live, public** | paid (see section 3) | yes, slowly on CPU | section 3 |

## 1. Replay site on GitHub Pages (the public link)

A static copy of the same UI. It replays real recorded answers: the SQL was written by the model in real runs, and the result tables are produced by running that SQL on the real database through the same guardrails. It also shows what the checks block, using the model's own attempts from the red-team run. Typing a new question gets a clear message that this page is a replay.

1. Create the saved answers (once, after the evaluation has run): `python -m eval.export_demo`, and commit `app/demo_answers.json` and `results/`.
2. In the GitHub repo: **Settings > Pages > Build and deployment > Source: GitHub Actions**.
3. Push to `main`. The **Pages** workflow builds `site/` with `python -m eval.export_static` and deploys it. The link is `https://<user>.github.io/<repo>/`.
4. Preview locally: `python -m eval.export_static --out site` then `python -m http.server -d site 8080`.

The build fails on purpose if there are no usable saved examples, so you never publish an empty page.

## 2. Live, on your own machine

```bash
ollama pull qwen2.5-coder:7b
uvicorn app.api:app --port 8000          # http://localhost:8000
```
Or with Docker: `docker compose up --build` (starts Ollama, pulls the model, serves the app; for the GPU, uncomment the `deploy:` block in `docker-compose.yml`). Use this for screenshots and the demo video.

## 3. Live and public (paid or card-required options)

* **Hugging Face PRO + Docker Space.** `deploy/Dockerfile.space` is a CPU-only single-container image with a 3B model baked in. It is built and exercised by the manual **Space image (manual)** GitHub workflow, which answered a live question in about 11 s on a 4-core runner. The free Space tier has 2 cores, so expect longer. Copy it to `Dockerfile` in the Space repo and add this header to the Space's `README.md`:
  ```
  ---
  title: Text-to-SQL Assistant
  sdk: docker
  app_port: 7860
  ---
  ```
* **Oracle Cloud "Always Free" ARM VM** (4 cores, 24 GB, card for verification): run `docker compose up -d` there. CPU-only, so the short `zero_shot` prompt is the practical choice (`DEFAULT_APPROACH=zero_shot`).
* Either way, keep `RATE_PER_MINUTE`, `MAX_CONCURRENT=1` and saved examples: CPU inference is slow, and the in-memory rate limiter is per process.

## Configuration (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `MODEL` | `qwen2.5-coder:7b` | Ollama model name |
| `OLLAMA_HOST` | `http://localhost:11434` | Model server |
| `DEFAULT_APPROACH` | `self_correct` | `zero_shot`, `fewshot`, `self_correct`, `docs`, `shots_only` |
| `ABORT_ON_UNSAFE` | `1` | Do not retry after a write or disallowed function is rejected |
| `RATE_PER_MINUTE` / `RATE_PER_DAY` | 10 / 300 | Per-IP limits |
| `MAX_CONCURRENT` / `QUEUE_WAIT_S` | 1 / 25 | Simultaneous model calls; seconds a request waits for a slot before a 503 |
| `ROW_LIMIT` / `QUERY_TIMEOUT_S` | 200 / 5 | Result cap; SQL time limit |
| `TRUST_PROXY` | 0 | Set to 1 behind a reverse proxy so the rate limiter sees the real client IP |

## Security notes
The service accepts only free text; model output is never executed without the parser check, the database file is opened read-only, responses carry a strict content-security policy, and the logs record approach, outcome and timing but not question text. There is no authentication; the rate limiter is in memory and per process, which is adequate for a small demo, not for production. The replay site has no server at all.
