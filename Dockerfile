# Company Teams approval bot — src/approval_bot on the Microsoft 365 Agents SDK (Python / aiohttp), built with uv
FROM python:3.14-slim
COPY --from=ghcr.io/astral-sh/uv:0.10.12 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=3978

WORKDIR /app
RUN useradd --create-home --uid 10001 bot

# dependencies first (cached until the lockfile changes)
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev --no-install-project

# the package itself (small; changes often)
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev
# The process runs as `bot`; it must own /app so Tilt can live-sync src/ and re-run `uv sync` in place.
RUN chown -R bot:bot /app
ENV PATH="/app/.venv/bin:$PATH" UV_CACHE_DIR=/tmp/uv-cache

USER bot
EXPOSE 3978

# Liveness probe: GET <Settings.route_prefix>/health (unauthenticated)
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import sys,urllib.request; from approval_bot.models import Settings; sys.exit(0 if urllib.request.urlopen(f'http://127.0.0.1:3978{Settings().route_prefix}/health', timeout=4).status == 200 else 1)"

CMD ["python", "-m", "approval_bot"]
