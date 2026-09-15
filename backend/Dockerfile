# Pin Debian bookworm: the unversioned `-slim` tag floats to the newest Debian
# (trixie), which renamed the Chromium runtime libs with a `t64` suffix
# (libasound2 -> libasound2t64, etc.) so the apt install below can't find them.
# Bookworm keeps the names this Dockerfile installs.
FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

# Build tools + curl, plus Chromium's OS libraries. We install these libs
# EXPLICITLY instead of via Playwright's `playwright install --with-deps`, because
# --with-deps pulls font packages (ttf-unifont, ttf-ubuntu-font-family) that aren't
# in Debian slim's repos and hard-fail the image build.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc curl \
    libnss3 libnspr4 libdbus-1-3 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libdrm2 libxcb1 libxkbcommon0 libatspi2.0-0 libx11-6 libxcomposite1 \
    libxdamage1 libxext6 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 \
    libcairo2 libasound2 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Chromium browser for the OPTIONAL browser-automation (auto-apply) engine — its OS
# libraries are apt-installed above, so we install only the browser binary (no
# --with-deps). `|| true` keeps a browser-download hiccup from ever failing the
# deploy: without the browser, automation just degrades to "assist" mode.
RUN python -m playwright install chromium || true

COPY . .

EXPOSE 8000
# Bind to the platform-assigned port. Render (and most PaaS) inject $PORT and probe
# THAT port for the health check; a hardcoded 8000 makes the probe time out and the
# deploy fail even though the app is up. Fall back to 8000 for local/compose runs.
HEALTHCHECK --interval=30s --timeout=5s --retries=5 \
    CMD curl -fsS http://localhost:${PORT:-8000}/health || exit 1

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
