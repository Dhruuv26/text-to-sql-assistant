FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY app ./app
COPY guardrails ./guardrails
COPY data ./data
RUN useradd --create-home --uid 1000 appuser
USER appuser
# The model server is a separate container (see docker-compose.yml); point OLLAMA_HOST elsewhere to use another host.
ENV OLLAMA_HOST=http://ollama:11434 MODEL=qwen2.5-coder:7b
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=4s --start-period=10s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"
CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8000"]
