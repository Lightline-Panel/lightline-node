# Lightline Node

Lightweight node agent for [Lightline VPN Panel](https://github.com/Lightline-Panel/lightline-panel). Install this on your remote servers to run Shadowsocks VPN — no external software (Outline, etc.) required.

## Architecture

```
┌─────────────────┐         ┌──────────────────────┐
│  Lightline Panel │ ──────▶ │  Lightline Node       │
│  (Central)       │  REST   │  (Remote Server)      │
│  Port 80/443     │ ◀────── │  Port 9090 (API)      │
└─────────────────┘         │  Port 8388 (SS)        │
                            │                        │
                            │  ┌──────────────────┐  │
                            │  │ ssserver (SS-Rust)│  │
                            │  │ Built-in, managed │  │
                            │  └──────────────────┘  │
                            └──────────────────────┘
```

The node agent runs a Shadowsocks server (shadowsocks-rust) internally and exposes a REST API for the panel to manage users:

- **Self-contained** — installs and runs `ssserver` automatically
- **User management** — add/remove users via REST API from the panel
- **Health reporting** — the panel checks if ss-server is running
- **Auto-config** — SS config file is generated and managed automatically

## Quick Install

```bash
sudo bash -c "$(curl -fsSL https://raw.githubusercontent.com/Lightline-Panel/lightline-node/main/install.sh)"
```

## Manual Install

### Requirements
- Python 3.10+
- Docker (recommended) or shadowsocks-rust installed locally

### Steps

1. Clone the repository:
```bash
git clone https://github.com/Lightline-Panel/lightline-node.git /opt/lightline-node
cd /opt/lightline-node
```

2. Configure:
```bash
cp .env.example .env
# Edit .env — set NODE_TOKEN and SS_PORT
```

3. Run with Docker (recommended):
```bash
docker compose up -d --build
```

Or run directly (requires shadowsocks-rust installed):
```bash
pip install -r requirements.txt
python main.py
```

## Configuration

| Variable | Default | Description |
|---|---|---|
| `NODE_PORT` | `9090` | Port the node agent API listens on |
| `NODE_HOST` | `0.0.0.0` | Bind address |
| `NODE_TOKEN` | (required) | Authentication token (set in panel when adding node) |
| `SS_PORT` | `8388` | Shadowsocks server port (clients connect here) |
| `SS_CONFIG_PATH` | `/etc/shadowsocks/config.json` | SS config file path (auto-managed) |
| `SSL_CERT_FILE` | `/var/lib/lightline-node/cert.pem` | TLS certificate for agent API |
| `SSL_KEY_FILE` | `/var/lib/lightline-node/key.pem` | TLS private key for agent API |

## API Endpoints

All endpoints require `Authorization: Bearer <NODE_TOKEN>` header.

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Node status and info |
| `GET` | `/health` | Health check (is ss-server running?) |
| `GET` | `/users` | List configured SS users |
| `POST` | `/users` | Add a user `{username, password}` |
| `DELETE` | `/users/{username}` | Remove a user |
| `POST` | `/restart` | Restart ss-server |

## License

MIT
