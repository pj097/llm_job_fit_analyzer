FROM python:3.14-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_PROJECT_ENVIRONMENT="/home/.venv"
ENV PATH="/home/.venv/bin:$PATH"

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --no-install-project --group screenshot

# Browser for scripts/capture_demo.py (full-page demo screenshot). Placed before
# `COPY . .` so editing app/source code doesn't invalidate this large layer
# (~200 MB of Chromium + apt libs); it only rebuilds when pyproject/uv.lock change.
RUN playwright install --with-deps chromium

COPY . .

RUN uv sync --all-extras --group screenshot

EXPOSE 8501
ENTRYPOINT ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]