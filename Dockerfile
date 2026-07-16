FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src

ENV PYTHONPATH=/app/src

RUN pip install --no-cache-dir .

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "agentic_ai_funnel_audit.api:app", "--host", "0.0.0.0", "--port", "8000"]
