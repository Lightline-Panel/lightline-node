FROM python:3.11-slim

WORKDIR /app

# Install outline-ss-server (multi-user chacha20-ietf-poly1305 on same port)
RUN apt-get update && apt-get install -y --no-install-recommends wget ca-certificates iptables iproute2 conntrack && \
    ARCH=$(dpkg --print-architecture) && \
    if [ "$ARCH" = "amd64" ]; then SS_ARCH="linux_x86_64"; \
    elif [ "$ARCH" = "arm64" ]; then SS_ARCH="linux_arm64"; \
    else SS_ARCH="linux_x86_64"; fi && \
    SS_VER="1.9.2" && \
    wget -q "https://github.com/OutlineFoundation/tunnel-server/releases/download/v${SS_VER}/outline-ss-server_${SS_VER}_${SS_ARCH}.tar.gz" -O /tmp/ss.tar.gz && \
    tar -xzf /tmp/ss.tar.gz -C /usr/local/bin/ outline-ss-server && \
    rm /tmp/ss.tar.gz && \
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
