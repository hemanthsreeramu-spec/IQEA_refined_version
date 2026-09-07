# IQEA — Azure container image.
#
# Python 3.12 is a HARD requirement, not a preference: utilities/Utilities_Xpath.py
# uses a backslash inside an f-string expression, which is only legal from 3.12
# (PEP 701). On 3.11 the app dies with SyntaxError at import.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # Modules do `from config...` / `from utilities...`; run_ai.bat sets
    # PYTHONPATH=%CD% locally and the container needs the same.
    PYTHONPATH=/app \
    # protobuf's native "upb" extension segfaults and silently kills the
    # Streamlit server (see the comment in run_ai.bat).
    PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python \
    # Switches the app to remote-browser + no-.env + desktop-recording-disabled.
    # Override from App Service application settings without rebuilding.
    IQEA_EXECUTION_TYPE=azure \
    TESSERACT_CMD=/usr/bin/tesseract \
    # App Service defaults: sidecar containers share a network namespace, so the
    # Grid Hub is on localhost. Compose/K8s override both to a service name.
    GRID_UPSTREAM=127.0.0.1:4444 \
    SELENIUM_REMOTE_URL=http://127.0.0.1:4444/wd/hub

RUN apt-get update && apt-get install -y --no-install-recommends \
        # pytesseract shells out to this binary — without it every OCR call
        # fails. This is the whole fix for "tesseract not working in azure".
        tesseract-ocr tesseract-ocr-eng \
        # opencv/scikit-image (PBI visual comparison) need these at import time
        libgl1 libglib2.0-0 \
        # nginx fronts both Streamlit and the Grid's noVNC on ONE port,
        # because App Service exposes only one.
        nginx supervisor \
        # envsubst — renders the Grid Hub address into nginx.conf at start
        gettext-base \
        curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies first so code edits do not invalidate the pip layer.
# The PEP 508 `sys_platform == "win32"` markers make pip skip pywin32 /
# pywinauto / comtypes here; without them this step HARD-FAILS on Linux.
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r requirements.txt

# .dockerignore keeps .env, .venv1/ and the *.tmp.* leftovers out of the image.
COPY . .

COPY deploy/nginx.conf.template /etc/nginx/nginx.conf.template
COPY deploy/supervisord.conf    /etc/supervisor/conf.d/iqea.conf
COPY deploy/entrypoint.sh       /usr/local/bin/entrypoint.sh
# Normalise line endings — the repo is edited on Windows, and a CRLF shebang
# makes the kernel fail the exec with a bare "not found".
RUN sed -i 's/\r$//' /usr/local/bin/entrypoint.sh \
    && chmod +x /usr/local/bin/entrypoint.sh

# App Service routes public traffic to this port (set WEBSITES_PORT=8000).
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
    CMD curl -fsS http://localhost:8000/_stcore/health || exit 1

CMD ["/usr/local/bin/entrypoint.sh"]
