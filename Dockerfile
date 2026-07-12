# syntax=docker/dockerfile:1

FROM python:3.14-slim
WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir -e .[prod]

COPY src/ ./src/
COPY config/ ./config/

EXPOSE 8000

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
