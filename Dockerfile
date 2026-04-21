FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DOWNLOADS_DIR=/data/downloads \
    APP_HOST=0.0.0.0 \
    APP_PORT=5000 \
    APP_DEBUG=false

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        nodejs \
        npm \
        git \
        fonts-noto-cjk \
        fontconfig \
        build-essential \
        zlib1g-dev \
        libjpeg62-turbo-dev \
        libfreetype6-dev \
    && git clone --depth 1 https://github.com/max32002/swei-fan-sans.git /tmp/swei-fan-sans \
    && mkdir -p /usr/local/share/fonts/swei-fan-sans \
    && regular_font="$(find /tmp/swei-fan-sans -type f -name 'SweiFanSansCJKtc-Regular.ttf' | head -n 1)" \
    && test -n "$regular_font" \
    && cp "$regular_font" /usr/local/share/fonts/swei-fan-sans/ \
    && fc-cache -f \
    && rm -rf /tmp/swei-fan-sans \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

RUN mkdir -p /data/downloads /data/cookies

EXPOSE 5000

CMD ["python", "app.py"]
