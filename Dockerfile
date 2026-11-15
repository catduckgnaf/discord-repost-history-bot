FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY bot.py ./
COPY cogs/ ./cogs/
COPY core/ ./core/
COPY README.md README.cs.md LICENSE ./

RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid 1000 --no-create-home app \
    && mkdir -p /app/data \
    && chown -R app:app /app

USER app

CMD ["python", "bot.py"]
