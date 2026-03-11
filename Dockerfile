FROM python:3.11-slim

WORKDIR /app

# Install shadowsocks-rust
RUN apt-get update && apt-get install -y --no-install-recommends wget ca-certificates xz-utils && \
    ARCH=$(dpkg --print-architecture) && \
    if [ "$ARCH" = "amd64" ]; then SS_ARCH="x86_64-unknown-linux-gnu"; \
    elif [ "$ARCH" = "arm64" ]; then SS_ARCH="aarch64-unknown-linux-gnu"; \
    else SS_ARCH="x86_64-unknown-linux-gnu"; fi && \
    SS_VER="1.20.4" && \
    wget -q "https://github.com/shadowsocks/shadowsocks-rust/releases/download/v${SS_VER}/shadowsocks-v${SS_VER}.${SS_ARCH}.tar.xz" -O /tmp/ss.tar.xz && \
    tar -xf /tmp/ss.tar.xz -C /usr/local/bin/ && \
    rm /tmp/ss.tar.xz && \
    apt-get purge -y wget && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create config directory
RUN mkdir -p /etc/shadowsocks

# Expose service API port + SS port
EXPOSE 62050 8388

CMD ["python", "main.py"]
