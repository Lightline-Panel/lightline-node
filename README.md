# Lightline Node

Lightweight node agent for [Lightline VPN Panel](https://github.com/Lightline-Panel/lightline-panel). Install this on your remote servers to manage Outline VPN instances from the central panel.

## Architecture

```
┌─────────────────┐         ┌──────────────────┐
│  Lightline Panel │ ──────▶ │  Lightline Node   │
│  (Central)       │  REST   │  (Remote Server)  │
│  Port 80/443     │ ◀────── │  Port 9090        │
└─────────────────┘         │                    │
                            │  ┌──────────────┐  │
                            │  │ Outline Server│  │
                            │  │ (SS Proxy)    │  │
                            │  └──────────────┘  │
                            └──────────────────┘
```

The node agent acts as a bridge between the panel and the Outline Server API running on the same machine. It provides:

- **Health reporting** — the panel checks node health via the agent
- **Key management** — create, delete, rename access keys via the panel
- **Traffic metrics** — pull transfer data from Outline
- **Certificate auth** — mutual TLS between panel and node

## Quick Install

```bash
sudo bash -c "$(curl -fsSL https://raw.githubusercontent.com/Lightline-Panel/lightline-node/main/install.sh)"
```

## Manual Install

### Requirements
- Python 3.10+
- Docker (for Outline Server)
- A running Outline Server instance

### Steps

1. Clone the repository:
```bash
git clone https://github.com/Lightline-Panel/lightline-node.git /opt/lightline-node
cd /opt/lightline-node
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure:
```bash
cp .env.example .env
# Edit .env with your Outline API URL and key
```

4. Run:
```bash
python main.py
```

Or use Docker:
```bash
docker compose up -d
```

## Configuration

| Variable | Default | Description |
|---|---|---|
| `NODE_PORT` | `9090` | Port the node agent listens on |
| `NODE_HOST` | `0.0.0.0` | Bind address |
| `NODE_TOKEN` | (required) | Authentication token (must match panel config) |
| `OUTLINE_API_URL` | (required) | Outline Server management API URL |
| `OUTLINE_API_KEY` | (required) | Outline Server API key |
| `SSL_CERT_FILE` | `/var/lib/lightline-node/cert.pem` | TLS certificate |
| `SSL_KEY_FILE` | `/var/lib/lightline-node/key.pem` | TLS private key |

## API Endpoints

All endpoints require `Authorization: Bearer <NODE_TOKEN>` header.

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Node status and info |
| `GET` | `/health` | Health check |
| `GET` | `/keys` | List all access keys |
| `POST` | `/keys` | Create an access key |
| `DELETE` | `/keys/{id}` | Delete an access key |
| `PUT` | `/keys/{id}/name` | Rename an access key |
| `PUT` | `/keys/{id}/data-limit` | Set data transfer limit |
| `GET` | `/metrics` | Get transfer metrics |
| `GET` | `/server` | Get Outline server info |

## License

MIT
