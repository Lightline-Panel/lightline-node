# Lightline Node

Proxy node for [Lightline VPN Panel](https://github.com/Lightline-Panel/lightline-panel). Follows the same architecture as [Marzban-node](https://github.com/Gozargah/Marzban-node) — certificate-based mTLS authentication, auto-generated SSL, and REST API.

## Architecture

```
┌─────────────────┐  mTLS   ┌──────────────────────┐
│  Lightline Panel │ ──────▶ │  Lightline Node       │
│  (Central)       │  REST   │  (Remote Server)      │
│  Port 80/443     │ ◀────── │  Port 62050 (API)     │
└─────────────────┘         │  Port 8388  (SS)       │
                            │                        │
                            │  ┌──────────────────┐  │
                            │  │ ssserver (SS-Rust)│  │
                            │  │ Auto-managed      │  │
                            │  └──────────────────┘  │
                            └──────────────────────┘
```

- **mTLS authentication** — Panel generates a certificate, admin copies it to the node. No tokens needed.
- **Auto-generated SSL** — Node creates its own cert/key on first run.
- **Self-contained** — Installs and manages `ssserver` (shadowsocks-rust) automatically.
- **Session-based control** — Panel calls `/connect` to establish a session, then controls SS via `/start`, `/stop`, `/restart`.

## Quick Install

```bash
sudo bash -c "$(curl -fsSL https://raw.githubusercontent.com/Lightline-Panel/lightline-node/main/lightline-node.sh)" @ install
```

## Manual Install

1. Clone and create data directory:
```bash
git clone https://github.com/Lightline-Panel/lightline-node.git ~/lightline-node
mkdir -p /var/lib/lightline-node
```

2. Get the panel certificate:
   - Go to **Nodes** page in Lightline Panel
   - Click **Certificate** button
   - Copy the certificate

3. Paste the certificate on the node server:
```bash
nano /var/lib/lightline-node/ssl_client_cert.pem
# Paste the certificate and save
```

4. Start the node:
```bash
cd ~/lightline-node
docker compose up -d
```

5. Return to the panel, add a new node with your server's IP address.

## Configuration

| Variable | Default | Description |
|---|---|---|
| `SERVICE_PORT` | `62050` | REST API port (panel connects here) |
| `SERVICE_HOST` | `0.0.0.0` | Bind address |
| `SS_PORT` | `8388` | Shadowsocks port (clients connect here) |
| `SSL_CERT_FILE` | `/var/lib/lightline-node/ssl_cert.pem` | Node's SSL cert (auto-generated) |
| `SSL_KEY_FILE` | `/var/lib/lightline-node/ssl_key.pem` | Node's SSL key (auto-generated) |
| `SSL_CLIENT_CERT_FILE` | (empty) | Panel's certificate for mTLS verification |
| `DEBUG` | `false` | Enable debug logging |

## API Endpoints

Authentication is via mTLS (panel's client certificate). Session-based endpoints require a `session_id` from `/connect`.

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/connect` | mTLS | Establish session, returns `session_id` |
| `POST` | `/disconnect` | mTLS | End session |
| `POST` | `/ping` | Session | Heartbeat |
| `GET` | `/health` | None | Health check |
| `GET` | `/server-info` | None | SS password, port, method |
| `GET` | `/status` | None | Full node status |
| `POST` | `/start` | Session | Start ss-server |
| `POST` | `/stop` | Session | Stop ss-server |
| `POST` | `/restart` | Session | Restart ss-server |

## License

MIT
