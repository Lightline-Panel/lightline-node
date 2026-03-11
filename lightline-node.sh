#!/usr/bin/env bash
set -e

# ══════════════════════════════════════════════════════════════
# Lightline Node — Management Script
# Usage:
#   Quick install:
#     sudo bash -c "$(curl -sL https://raw.githubusercontent.com/Lightline-Panel/lightline-node/main/lightline-node.sh)" @ install
#   After install, use:
#     lightline-node <command>
# ══════════════════════════════════════════════════════════════

APP_NAME="lightline-node"
INSTALL_DIR="/opt/lightline-node"
DATA_DIR="/var/lib/lightline-node"
COMPOSE_FILE="$INSTALL_DIR/docker-compose.yml"
ENV_FILE="$INSTALL_DIR/.env"
REPO_URL="https://github.com/Lightline-Panel/lightline-node.git"
SCRIPT_URL="https://raw.githubusercontent.com/Lightline-Panel/lightline-node/main/lightline-node.sh"

# ── Colors ──

colorize() {
    local color=$1; local text=$2
    case $color in
        red)     printf "\e[91m%s\e[0m\n" "$text" ;;
        green)   printf "\e[92m%s\e[0m\n" "$text" ;;
        yellow)  printf "\e[93m%s\e[0m\n" "$text" ;;
        blue)    printf "\e[94m%s\e[0m\n" "$text" ;;
        cyan)    printf "\e[96m%s\e[0m\n" "$text" ;;
        *)       echo "$text" ;;
    esac
}

# ── Helpers ──

check_root() {
    if [ "$(id -u)" != "0" ]; then
        colorize red "Error: This command must be run as root."
        exit 1
    fi
}

detect_compose() {
    if docker compose version >/dev/null 2>&1; then
        COMPOSE="docker compose"
    elif docker-compose version >/dev/null 2>&1; then
        COMPOSE="docker-compose"
    else
        colorize red "Error: docker compose not found. Install Docker first."
        exit 1
    fi
}

is_installed() {
    [ -d "$INSTALL_DIR" ] && [ -f "$COMPOSE_FILE" ]
}

check_installed() {
    if ! is_installed; then
        colorize red "Lightline Node is not installed. Run: lightline-node install"
        exit 1
    fi
}

install_node_script() {
    colorize blue "Installing 'lightline-node' command..."
    curl -sSL "$SCRIPT_URL" | install -m 755 /dev/stdin /usr/local/bin/lightline-node 2>/dev/null || {
        if [ -f "$INSTALL_DIR/lightline-node.sh" ]; then
            install -m 755 "$INSTALL_DIR/lightline-node.sh" /usr/local/bin/lightline-node
        fi
    }
    colorize green "'lightline-node' command installed."
}

# ══════════════════════════════════════════════════════════════
# COMMANDS
# ══════════════════════════════════════════════════════════════

install_cmd() {
    check_root

    colorize cyan "══════════════════════════════════════════════"
    colorize cyan "   Lightline Node — Installer"
    colorize cyan "══════════════════════════════════════════════"
    echo ""

    if is_installed; then
        colorize yellow "Lightline Node is already installed at $INSTALL_DIR"
        printf "Do you want to update instead? (y/N): "
        read -r confirm
        if [[ "$confirm" =~ ^[Yy]$ ]]; then
            update_cmd
            return
        fi
        colorize yellow "Installation cancelled."
        return
    fi

    # Install Docker if needed
    if ! command -v docker &>/dev/null; then
        colorize blue "Installing Docker..."
        curl -fsSL https://get.docker.com | sh
        systemctl enable docker
        systemctl start docker
        colorize green "Docker installed"
    else
        colorize green "Docker already installed: $(docker --version)"
    fi

    # Install git if needed
    if ! command -v git &>/dev/null; then
        colorize blue "Installing git..."
        apt-get update -qq && apt-get install -y -qq git
        colorize green "Git installed"
    fi

    # Clone repository
    colorize blue "Cloning Lightline Node repository..."
    git clone "$REPO_URL" "$INSTALL_DIR"
    colorize green "Repository cloned to $INSTALL_DIR"

    cd "$INSTALL_DIR"

    # Configure .env
    if [ ! -f "$ENV_FILE" ]; then
        colorize blue "Setting up configuration..."
        echo ""

        local service_port=62050
        printf "  Service port [%s]: " "$service_port"
        read -r input_port
        [ -n "$input_port" ] && service_port="$input_port"

        local ss_port=8388
        printf "  Shadowsocks port [%s]: " "$ss_port"
        read -r input_ss
        [ -n "$input_ss" ] && ss_port="$input_ss"

        cat > "$ENV_FILE" <<EOF
# Lightline Node Configuration
# Generated on $(date -u +"%Y-%m-%dT%H:%M:%SZ")

SERVICE_PORT=$service_port
SERVICE_HOST=0.0.0.0

SS_PORT=$ss_port
SS_CONFIG_PATH=/etc/shadowsocks/config.json

SSL_CERT_FILE=/var/lib/lightline-node/ssl_cert.pem
SSL_KEY_FILE=/var/lib/lightline-node/ssl_key.pem
SSL_CLIENT_CERT_FILE=/var/lib/lightline-node/ssl_client_cert.pem
EOF

        chmod 600 "$ENV_FILE"
        colorize green "Configuration saved"
    fi

    # Create data directory
    mkdir -p "$DATA_DIR"

    # Prompt for panel certificate
    local cert_file="$DATA_DIR/ssl_client_cert.pem"
    if [ ! -f "$cert_file" ]; then
        echo ""
        colorize yellow "══════════════════════════════════════════════"
        colorize yellow "  Panel Certificate Required"
        colorize yellow "══════════════════════════════════════════════"
        echo ""
        echo "  Go to Lightline Panel → Nodes → Certificate"
        echo "  Copy the certificate and paste it below."
        echo "  (Paste all lines, then press Enter on an empty line)"
        echo ""

        local cert_content=""
        local line=""
        while IFS= read -r line; do
            [ -z "$line" ] && break
            cert_content="${cert_content}${line}"$'\n'
        done

        if [ -z "$cert_content" ]; then
            colorize yellow "No certificate provided. You can add it later:"
            colorize yellow "  nano $cert_file"
        else
            echo "$cert_content" > "$cert_file"
            chmod 600 "$cert_file"
            colorize green "Panel certificate saved to $cert_file"
        fi
    fi

    # Build and start
    detect_compose
    colorize blue "Building and starting Lightline Node..."
    $COMPOSE up -d --build

    # Install the lightline-node command
    install_node_script

    local server_ip
    server_ip=$(curl -s ifconfig.me 2>/dev/null || hostname -I 2>/dev/null | awk '{print $1}' || echo "YOUR_IP")

    echo ""
    colorize cyan "══════════════════════════════════════════════"
    colorize green "  Lightline Node — Installed!"
    colorize cyan "══════════════════════════════════════════════"
    echo ""
    echo "  Server IP:      $server_ip"
    echo "  Service Port:   $(grep SERVICE_PORT "$ENV_FILE" | head -1 | cut -d= -f2)"
    echo "  SS Port:        $(grep SS_PORT "$ENV_FILE" | head -1 | cut -d= -f2)"
    echo "  Install dir:    $INSTALL_DIR"
    echo "  Data dir:       $DATA_DIR"
    echo ""
    if [ -f "$DATA_DIR/ssl_client_cert.pem" ]; then
        colorize green "  Panel certificate: ✓ installed"
    else
        colorize yellow "  Panel certificate: ✗ not installed"
        colorize yellow "  Paste it to: $DATA_DIR/ssl_client_cert.pem"
    fi
    echo ""
    colorize yellow "  Now add this node in the Lightline Panel:"
    echo "    Name:    $(hostname)"
    echo "    IP:      $server_ip"
    echo "    Country: <your country code>"
    echo ""
    colorize cyan "  Type 'lightline-node' to see all commands."
    colorize cyan "══════════════════════════════════════════════"
    echo ""
}

uninstall_cmd() {
    check_root
    check_installed

    echo ""
    colorize red "══════════════════════════════════════════════"
    colorize red "  WARNING: This will completely remove"
    colorize red "  Lightline Node from this server."
    colorize red "══════════════════════════════════════════════"
    echo ""

    printf "Type 'DELETE' to confirm: "
    read -r confirm
    if [ "$confirm" != "DELETE" ]; then
        colorize yellow "Uninstall cancelled."
        return
    fi

    cd "$INSTALL_DIR"
    detect_compose

    colorize blue "Stopping services..."
    $COMPOSE down -v 2>&1 || true

    colorize blue "Removing installation..."
    rm -rf "$INSTALL_DIR"
    rm -rf "$DATA_DIR"

    if [ -f /usr/local/bin/lightline-node ]; then
        rm -f /usr/local/bin/lightline-node
    fi

    echo ""
    colorize green "Lightline Node has been completely removed."
    echo ""
}

update_cmd() {
    check_root
    check_installed
    cd "$INSTALL_DIR"
    detect_compose

    colorize blue "Pulling latest changes..."
    git stash 2>/dev/null || true
    git pull origin main
    colorize green "Repository updated"

    colorize blue "Rebuilding..."
    $COMPOSE build
    $COMPOSE up -d

    install_node_script

    echo ""
    colorize green "Lightline Node updated successfully."
    echo ""
}

start_cmd() {
    check_root; check_installed; cd "$INSTALL_DIR"; detect_compose
    colorize blue "Starting Lightline Node..."
    $COMPOSE up -d
    colorize green "Started."
}

stop_cmd() {
    check_root; check_installed; cd "$INSTALL_DIR"; detect_compose
    colorize blue "Stopping Lightline Node..."
    $COMPOSE down
    colorize green "Stopped."
}

restart_cmd() {
    check_root; check_installed; cd "$INSTALL_DIR"; detect_compose
    colorize blue "Restarting Lightline Node..."
    $COMPOSE down
    $COMPOSE up -d
    colorize green "Restarted."
}

status_cmd() {
    check_installed; cd "$INSTALL_DIR"; detect_compose
    echo ""
    colorize cyan "Lightline Node — Status"
    colorize cyan "═══════════════════════"
    echo ""
    $COMPOSE ps
    echo ""
}

logs_cmd() {
    check_installed; cd "$INSTALL_DIR"; detect_compose
    $COMPOSE logs -f --tail=100
}

config_cmd() {
    check_root; check_installed
    local subcmd="${1:-edit}"
    case "$subcmd" in
        edit)
            if command -v nano &>/dev/null; then nano "$ENV_FILE"
            elif command -v vi &>/dev/null; then vi "$ENV_FILE"
            else cat "$ENV_FILE"; fi
            ;;
        show) cat "$ENV_FILE" ;;
        *) echo "Usage: lightline-node config [edit|show]" ;;
    esac
}

version_cmd() {
    echo "Lightline Node"
    echo "Script version: 1.0.0"
    if is_installed; then
        cd "$INSTALL_DIR"
        echo "Install version: $(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
    fi
}

show_help() {
    echo ""
    colorize cyan "  Lightline Node — Management CLI"
    colorize cyan "  ═══════════════════════════════════"
    echo ""
    echo "  Usage: lightline-node <command>"
    echo ""
    colorize green "  Core commands:"
    echo "    install          Install Lightline Node on this server"
    echo "    update           Update to the latest version"
    echo "    uninstall        Completely remove Lightline Node"
    echo "    restart          Restart the node service"
    echo "    stop             Stop the node service"
    echo "    start            Start the node service"
    echo ""
    colorize green "  Info commands:"
    echo "    status           Show service status"
    echo "    logs             View logs"
    echo "    version          Show version info"
    echo ""
    colorize green "  Config commands:"
    echo "    config edit      Edit .env configuration"
    echo "    config show      Show current configuration"
    echo ""
    colorize green "  Script commands:"
    echo "    install-script   Install only the CLI command"
    echo "    help             Show this help message"
    echo ""
    colorize cyan "  Quick install:"
    echo '    sudo bash -c "$(curl -sL https://raw.githubusercontent.com/Lightline-Panel/lightline-node/main/lightline-node.sh)" @ install'
    echo ""
}

install_script_cmd() {
    check_root
    install_node_script
}

# ── Main ──

main() {
    local command="${1:-}"
    shift 2>/dev/null || true
    case "$command" in
        install)          install_cmd "$@" ;;
        uninstall|remove) uninstall_cmd "$@" ;;
        update|upgrade)   update_cmd "$@" ;;
        start|up)         start_cmd "$@" ;;
        stop|down)        stop_cmd "$@" ;;
        restart)          restart_cmd "$@" ;;
        status)           status_cmd "$@" ;;
        logs|log)         logs_cmd "$@" ;;
        config|env)       config_cmd "$@" ;;
        version|-v)       version_cmd "$@" ;;
        install-script)   install_script_cmd "$@" ;;
        help|-h|--help)   show_help ;;
        "")               show_help ;;
        *)
            colorize red "Unknown command: $command"
            echo "Run 'lightline-node help' for usage."
            exit 1
            ;;
    esac
}

main "$@"
