#!/bin/sh
ollama serve >/tmp/ollama.log 2>&1 &
for i in $(seq 1 90); do
  curl -sf http://127.0.0.1:11434/api/tags >/dev/null && break
  sleep 1
done
exec uvicorn app.api:app --host 0.0.0.0 --port 7860
