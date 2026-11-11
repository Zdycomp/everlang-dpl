FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential gdb git ca-certificates jq \
        python3 python3-pytest python3-pyflakes \
        ruby sqlite3 \
        openjdk-25-jdk-headless maven \
    && ln -s "$(ls -d /usr/lib/jvm/java-25-openjdk-*)" /usr/lib/jvm/jdk-25 \
    && rm -rf /var/lib/apt/lists/*

ENV JAVA_HOME=/usr/lib/jvm/jdk-25
ENV PATH=/usr/lib/jvm/jdk-25/bin:$PATH
