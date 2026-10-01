FROM python:3.12-slim AS builder

WORKDIR /build
RUN pip install --no-cache-dir hatchling
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip wheel --no-cache-dir --wheel-dir /wheels .

FROM python:3.12-slim AS runtime

RUN groupadd --system app && useradd --system --gid app --create-home app

WORKDIR /app
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/*.whl && rm -rf /wheels

RUN mkdir -p /data /config && chown -R app:app /data /config
USER app

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 WEB_HOST=0.0.0.0 WEB_PORT=8080 \
    DATABASE_PATH=/data/listings.db KEYWORD_SEED_PATH=/config/keywords.yaml
EXPOSE 8080

HEALTHCHECK --interval=120s --timeout=10s --start-period=90s --retries=3 \
    CMD python -m mercari_alert_bot.healthcheck

ENTRYPOINT ["python", "-m", "mercari_alert_bot"]
