FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/knowledge_base/raw \
    /app/knowledge_base/analyzed \
    /app/knowledge_base/translated \
    /app/knowledge_base/obsidian \
    /app/knowledge_base/vectors \
    /app/shared/logs

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE 5070

CMD ["python", "analyzer/pipeline.py", "--rss"]
