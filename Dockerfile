FROM python:3.11-slim

WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY static ./static

ENV PORT=8080
CMD exec uvicorn --factory app.main:production_app --host 0.0.0.0 --port ${PORT}
