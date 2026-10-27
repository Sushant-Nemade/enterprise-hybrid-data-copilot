FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN groupadd --gid 10001 copilotuser && \
    useradd --uid 10001 --gid copilotuser --create-home --shell /usr/sbin/nologin copilotuser

COPY pyproject.toml README.md LICENSE MANIFEST.in ./
COPY src ./src
COPY data ./data
COPY artifacts ./artifacts

RUN pip install --no-cache-dir . && \
    chown -R copilotuser:copilotuser /app

USER copilotuser
EXPOSE 8000

CMD ["python", "-m", "uvicorn", "copilot.api:app", "--host", "0.0.0.0", "--port", "8000"]
