# Deploying a public demo

The expensive part is the language model; the database is a 1 MB SQLite file. Everything below uses free, public components and needs **no API keys**.

## Choose where the model runs

| Option | Cost | Speed | Notes |
|---|---|---|---|
| **Your own machine** (Docker Compose, GPU) | free | ~3 s per question (RTX 4060, 7B) | Best accuracy; use for the demo video and screenshots. Not a stable public link. |
| **Hugging Face Docker Space, CPU, 3B model baked in** | free, no card | slow (see below) | A stable public link. Use `zero_shot`, saved example answers, and a strict rate limit. |
| **Oracle Cloud "Always Free" ARM VM** (4 cores, 24 GB) | free, needs a card for sign-up verification | slow on CPU | Fits a 7B model; same CPU-latency caveat. |

**Be realistic about CPU latency.** A free CPU host reads a prompt at a few tens of tokens per second. The `zero_shot` prompt (~700 tokens) plus a 3B model typically takes tens of seconds per question; the `self_correct` prompt (~1,800 tokens) several times that. That is why the Space template defaults to `zero_shot`, queues one request at a time, rate-limits hard, and relies on **saved example answers** (served instantly, still validated by the guardrails) so a visitor sees a working product in one click even when the model is slow.

## 1. Run locally with Docker (recommended first test)

```bash
docker compose up --build           # open http://localhost:8000
# GPU: uncomment the `deploy:` block in docker-compose.yml (NVIDIA container toolkit required)
```
Switch model: `MODEL=qwen2.5-coder:3b docker compose up --build`.

## 2. Create the saved example answers (do this once, on your machine)

After running the evaluation: `python -m eval.export_demo --model qwen2.5-coder:7b --approach self_correct`. It writes `app/demo_answers.json` with answers the harness scored **correct**, so the example chips are instant and honest. Commit that file.

## 3. Hugging Face Space (free public link)

1. Create a new Space, SDK **Docker**, hardware **CPU basic**.
2. Clone it, copy this repository into it, and move the Space image file to the root: `cp deploy/Dockerfile.space Dockerfile` (overwrite).
3. Put this at the very top of the Space's `README.md` (Hugging Face reads it as configuration):
   ```
   ---
   title: Text-to-SQL Assistant
   sdk: docker
   app_port: 7860
   ---
   ```
4. Push. The first build downloads the model (a few GB); later starts are fast. Free Spaces sleep after inactivity, so the first visit after a quiet period takes a while: say so in the README.
5. `deploy/Dockerfile.space` is a **template that has not been run by the author yet**. No local Docker needed to test it: push the repo, open the **Actions** tab, choose **Space image (manual)**, and press **Run workflow**. It builds the image, waits for the model, and asks one live question on a CPU runner; the log shows how long that takes. Locally, the equivalent is: `docker build -f deploy/Dockerfile.space -t t2s-space .` then `docker run -p 7860:7860 t2s-space`. Things to verify: the model is present (`curl localhost:7860/api/health` shows `"llm_ready": true`), and one example answers instantly.

## Configuration (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `MODEL` | `qwen2.5-coder:7b` | Ollama model name |
| `OLLAMA_HOST` | `http://localhost:11434` | Model server |
| `DEFAULT_APPROACH` | `self_correct` | `zero_shot`, `fewshot`, `self_correct`, `docs`, `shots_only` |
| `RATE_PER_MINUTE` / `RATE_PER_DAY` | 10 / 300 | Per-IP limits |
| `MAX_CONCURRENT` / `QUEUE_WAIT_S` | 1 / 25 | Simultaneous model calls; seconds a request waits for a slot before a 503 |
| `ROW_LIMIT` / `QUERY_TIMEOUT_S` | 200 / 5 | Result cap; SQL time limit |
| `TRUST_PROXY` | 0 | Set to 1 behind a reverse proxy so the rate limiter sees the real client IP |

## Security notes
The service accepts only free text; model output is never executed without the parser check, the database file is opened read-only, responses carry a strict content-security policy, and the logs record approach, outcome and timing but not question text. There is no authentication; the rate limiter is in memory and per process, which is adequate for a small demo, not for production.
