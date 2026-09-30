FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py build.py answers.py ./
COPY static/ ./static/

ENV PORT=8080 TTL_HOURS=24
EXPOSE 8080
CMD uvicorn server:app --host 0.0.0.0 --port ${PORT}
