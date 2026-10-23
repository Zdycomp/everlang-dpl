FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential gdb git ca-certificates jq \
        python3 python3-pytest python3-pyflakes \
        ruby sqlite3 \
        openjdk-21-jdk-headless openjdk-25-jdk-headless maven \
    && ln -s "$(ls -d /usr/lib/jvm/java-21-openjdk-*)" /usr/lib/jvm/jdk-21 \
    && ln -s "$(ls -d /usr/lib/jvm/java-25-openjdk-*)" /usr/lib/jvm/jdk-25 \
    && rm -rf /var/lib/apt/lists/*

# JDK 21 is the default because the 6-android-kotlin build (Gradle 8.14.3) fails on JDK 25.
# 5-runtime-java compiles with --release 25; run_all.py gives Maven the JDK 25 (ADR-001).
ENV JAVA_HOME=/usr/lib/jvm/jdk-21
ENV PATH=/usr/lib/jvm/jdk-21/bin:$PATH
