FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Ensure folders exist (state/chunks/md/logs)
RUN mkdir -p data/md data/chunks data/logs

# Run once and exit
CMD ["python", "main.py"]
