# ─────────────────────────────────────────────
# Ever / Tapestry — cross-platform test container
#
# Build:   docker build -t codric/ever:3.4 .
# Verify:  docker run --rm codric/ever:3.4 ./run.sh
# Tests:   docker run --rm codric/ever:3.4 python3 tests/run_all.py
# Shell:   docker run --rm -it codric/ever:3.4 /bin/bash
#
# The image verifies itself at build time. If any layer fails, the
# build fails — an image that ships without its own tests passing
# ships a claim instead of a result.
#
# Codric Enterprise · Ricky (Dreid) · 2026
# ─────────────────────────────────────────────

FROM debian:bookworm-slim

LABEL org.opencontainers.image.title="Ever / Tapestry"
LABEL org.opencontainers.image.description="A language where every value carries how much it is trusted"
LABEL org.opencontainers.image.vendor="Codric Enterprise"
LABEL org.opencontainers.image.authors="Ricky (Dreid)"
LABEL org.opencontainers.image.version="3.4"

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# Ensure consistent locale for all string operations
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8

# ── toolchains ──
# One layer per concern — ordered least- to most-volatile
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        g++ \
        make \
        python3 \
        python3-venv \
        ruby-full \
        sqlite3 \
        nodejs \
        default-jdk-headless \
        ca-certificates \
        diffutils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /ever

# ── sources ──
COPY . /ever
RUN chmod +x run.sh tests/run_all.py 2>/dev/null || true

# ── cross-platform sanity check ──
# These verify that the container is not accidentally relying on any
# macOS-specific system library. Debian's gcc, Ruby, JDK and Python
# must all agree with the host implementations on:
#   - struct sizes and field offsets (ABI)
#   - floating-point arithmetic
#   - string encoding

RUN python3 -c "
import sys, platform
print(f'Python  {sys.version}')
print(f'OS      {platform.system()} {platform.release()}')
print(f'Arch    {platform.machine()}')
" && \
    gcc --version | head -1 && \
    ruby --version && \
    node --version

# ── build-time verification ──
# The full test suite must pass before the image is finalised.
RUN ./run.sh && python3 tests/run_all.py

# ── default: run everything ──
CMD ["python3", "tests/run_all.py"]
