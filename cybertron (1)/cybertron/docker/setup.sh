#!/bin/bash
# Cybertron Bug Bounty Hunter — Auto-Setup Script
# =================================================
# This script will:
#   1. Check if Docker is installed (install if not)
#   2. Check if Docker Compose is installed (install if not)
#   3. Create required directories
#   4. Build all container images
#   5. Pull wordlists and templates
#   6. Start the Cybertron Bug Bounty platform
#   7. Display access URLs and first steps

set -e

CYBERTRON_DIR="${HOME}/.cybertron"
REPORTS_DIR="${CYBERTRON_DIR}/reports"
WORDLISTS_DIR="${CYBERTRON_DIR}/wordlists"
EXPORTS_DIR="${CYBERTRON_DIR}/exports"
LOGS_DIR="${CYBERTRON_DIR}/logs"
CONFIGS_DIR="${CYBERTRON_DIR}/configs"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'
BOLD='\033[1m'

print_banner() {
    echo ""
    echo -e "${CYAN}${BOLD}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}${BOLD}║         CYBERTRON BUG BOUNTY HUNTER — SETUP                ║${NC}"
    echo -e "${CYAN}${BOLD}║         Auto-Install • Docker • HackerOne Ready            ║${NC}"
    echo -e "${CYAN}${BOLD}╚══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_ok() {
    echo -e "${GREEN}[OK]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# ─── Check OS ────────────────────────────────────────────────────────────────
detect_os() {
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        if [ -f /etc/os-release ]; then
            . /etc/os-release
            OS=$NAME
        else
            OS="Linux"
        fi
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        OS="macOS"
    else
        OS="Unknown"
    fi
    log_info "Detected OS: $OS"
}

# ─── Install Docker ──────────────────────────────────────────────────────────
install_docker() {
    log_info "Docker not found. Installing..."

    if [[ "$OS" == *"Ubuntu"* ]] || [[ "$OS" == *"Debian"* ]]; then
        log_info "Installing Docker for Debian/Ubuntu..."
        sudo apt-get update
        sudo apt-get install -y ca-certificates curl gnupg
        sudo install -m 0755 -d /etc/apt/keyrings
        curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
        echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
        sudo apt-get update
        sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

    elif [[ "$OS" == *"Kali"* ]]; then
        log_info "Installing Docker for Kali Linux..."
        sudo apt-get update
        sudo apt-get install -y docker.io docker-compose
        sudo systemctl enable docker --now

    elif [[ "$OS" == *"Fedora"* ]] || [[ "$OS" == *"Red Hat"* ]] || [[ "$OS" == *"CentOS"* ]]; then
        log_info "Installing Docker for RHEL/Fedora..."
        sudo dnf -y install dnf-plugins-core
        sudo dnf config-manager --add-repo https://download.docker.com/linux/fedora/docker-ce.repo
        sudo dnf install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
        sudo systemctl start docker
        sudo systemctl enable docker

    elif [[ "$OS" == "macOS" ]]; then
        log_warn "Please install Docker Desktop manually from https://www.docker.com/products/docker-desktop"
        log_warn "Then re-run this script."
        exit 1
    else
        log_error "Unsupported OS. Please install Docker manually: https://docs.docker.com/get-docker/"
        exit 1
    fi

    # Add user to docker group
    sudo usermod -aG docker $USER 2>/dev/null || true
    log_ok "Docker installed successfully"
}

# ─── Check Docker ───────────────────────────────────────────────────────────
check_docker() {
    if ! command -v docker &> /dev/null; then
        install_docker
    else
        log_ok "Docker is installed ($(docker --version))"
    fi

    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        log_info "Installing Docker Compose..."
        sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
        sudo chmod +x /usr/local/bin/docker-compose
    fi

    if docker compose version &> /dev/null; then
        COMPOSE_CMD="docker compose"
    else
        COMPOSE_CMD="docker-compose"
    fi
    log_ok "Docker Compose ready ($COMPOSE_CMD)"
}

# ─── Create Directories ─────────────────────────────────────────────────────
setup_directories() {
    log_info "Creating Cybertron directories..."
    mkdir -p "$CYBERTRON_DIR"/{reports,wordlists,exports,logs,configs,tools}
    mkdir -p "$REPORTS_DIR"/{markdown,json,pdf}
    mkdir -p "$WORDLISTS_DIR"/{dns,web,brute,api}
    log_ok "Directories created at $CYBERTRON_DIR"
}

# ─── Create Config Files ────────────────────────────────────────────────────
setup_configs() {
    log_info "Setting up configuration files..."

    # Auth token
    if [ ! -f "$CYBERTRON_DIR/auth-token" ]; then
        TOKEN=$(openssl rand -hex 32 2>/dev/null || cat /dev/urandom | tr -dc 'a-zA-Z0-9' | fold -w 64 | head -n 1)
        echo "$TOKEN" > "$CYBERTRON_DIR/auth-token"
        log_ok "Generated auth token: ${TOKEN:0:16}..."
    fi

    # Environment file
    if [ ! -f "$CYBERTRON_DIR/.env" ]; then
        cat > "$CYBERTRON_DIR/.env" << 'EOF'
# Cybertron Bug Bounty Configuration
# ==================================

# NVIDIA NIM API (for LLM agent)
NIM_API_KEY=your_nim_api_key_here

# HackerOne API
HACKERONE_API_KEY=your_hackerone_api_key_here
HACKERONE_USERNAME=your_hackerone_username

# Database
DB_PASSWORD=cybertron_secret_change_me

# Optional: Burp Collaborator
COLLABORATOR_DOMAIN=

# Rate Limiting
RATE_LIMIT_PER_MINUTE=30

# Output Sanitization
SANITIZE_OUTPUT=true
PRESERVE_PRIVATE_IPS=true
EOF
        log_ok "Created .env template at $CYBERTRON_DIR/.env"
        log_warn "Please edit $CYBERTRON_DIR/.env and add your API keys!"
    fi

    # Webhook config
    if [ ! -f "$CYBERTRON_DIR/webhooks.json" ]; then
        cat > "$CYBERTRON_DIR/webhooks.json" << 'EOF'
{
  "webhooks": [
    {
      "name": "slack-alerts",
      "url": "https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK",
      "events": ["finding", "session_completed"],
      "headers": {"Content-Type": "application/json"},
      "enabled": false
    }
  ]
}
EOF
        log_ok "Created webhook config template"
    fi

    # Bug bounty targets config
    if [ ! -f "$CYBERTRON_DIR/configs/targets.json" ]; then
        cat > "$CYBERTRON_DIR/configs/targets.json" << 'EOF'
{
  "targets": [
    {
      "name": "example-program",
      "platform": "hackerone",
      "handle": "example",
      "scope": ["*.example.com"],
      "out_of_scope": ["blog.example.com", "help.example.com"],
      "severity_filter": ["critical", "high", "medium"],
      "enabled": false
    }
  ],
  "global_settings": {
    "max_concurrent_scans": 3,
    "scan_timeout_minutes": 60,
    "auto_report": false,
    "report_template": "hackerone"
  }
}
EOF
        log_ok "Created targets config template"
    fi
}

# ─── Download Wordlists ─────────────────────────────────────────────────────
download_wordlists() {
    log_info "Downloading wordlists..."

    cd "$WORDLISTS_DIR"

    # DNS wordlists
    if [ ! -f "dns/subdomains-top1million-5000.txt" ]; then
        curl -sL "https://raw.githubusercontent.com/danielmiessler/SecLists/master/Discovery/DNS/subdomains-top1million-5000.txt" -o dns/subdomains-top1million-5000.txt 2>/dev/null || true
    fi

    # Web wordlists
    if [ ! -f "web/common.txt" ]; then
        curl -sL "https://raw.githubusercontent.com/danielmiessler/SecLists/master/Discovery/Web-Content/common.txt" -o web/common.txt 2>/dev/null || true
    fi

    # API wordlists
    if [ ! -f "api/api-endpoints.txt" ]; then
        curl -sL "https://raw.githubusercontent.com/danielmiessler/SecLists/master/Discovery/Web-Content/api/api-endpoints.txt" -o api/api-endpoints.txt 2>/dev/null || true
    fi

    # Brute force wordlists
    if [ ! -f "brute/rockyou.txt" ]; then
        log_info "RockYou wordlist is large. Skipping auto-download."
        log_info "Download manually: curl -L https://github.com/brannondorsey/naive-hashcat/releases/download/data/rockyou.txt -o $WORDLISTS_DIR/brute/rockyou.txt"
    fi

    log_ok "Wordlists ready"
}

# ─── Build Images ───────────────────────────────────────────────────────────
build_images() {
    log_info "Building Cybertron container images..."
    log_warn "This may take 10-20 minutes on first run..."

    $COMPOSE_CMD build --parallel

    log_ok "All images built successfully"
}

# ─── Start Services ─────────────────────────────────────────────────────────
start_services() {
    log_info "Starting Cybertron Bug Bounty platform..."

    $COMPOSE_CMD up -d

    log_ok "Services started"

    # Wait for health checks
    log_info "Waiting for services to be healthy..."
    sleep 5

    for i in {1..30}; do
        if docker ps --format "{{.Names}}" | grep -q "cybertron-gateway"; then
            HEALTH=$(docker inspect --format='{{.State.Health.Status}}' cybertron-gateway 2>/dev/null || echo "starting")
            if [ "$HEALTH" == "healthy" ]; then
                log_ok "Gateway is healthy"
                break
            fi
        fi
        sleep 2
    done
}

# ─── Display Info ───────────────────────────────────────────────────────────
show_info() {
    echo ""
    echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}${BOLD}║              CYBERTRON IS READY FOR BUG BOUNTY             ║${NC}"
    echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${CYAN}Access Points:${NC}"
    echo -e "  ${BOLD}Web UI:${NC}     http://localhost:8080/web_ui.html"
    echo -e "  ${BOLD}Gateway WS:${NC} ws://localhost:8765"
    echo -e "  ${BOLD}Auth Token:${NC} $(cat $CYBERTRON_DIR/auth-token | cut -c1-16)..."
    echo ""
    echo -e "${CYAN}Directories:${NC}"
    echo -e "  ${BOLD}Reports:${NC}    $REPORTS_DIR"
    echo -e "  ${BOLD}Wordlists:${NC}  $WORDLISTS_DIR"
    echo -e "  ${BOLD}Exports:${NC}    $EXPORTS_DIR"
    echo -e "  ${BOLD}Configs:${NC}    $CONFIGS_DIR"
    echo ""
    echo -e "${CYAN}Quick Start:${NC}"
    echo -e "  1. Edit ${YELLOW}$CYBERTRON_DIR/.env${NC} and add your API keys"
    echo -e "  2. Edit ${YELLOW}$CYBERTRON_DIR/configs/targets.json${NC} and add targets"
    echo -e "  3. Open ${YELLOW}http://localhost:8080/web_ui.html${NC}"
    echo -e "  4. Paste your auth token and connect"
    echo -e "  5. Run: ${YELLOW}/add-tool projectdiscovery/nuclei scan${NC}"
    echo -e "  6. Start hunting: ${YELLOW}Scan hackerone.com for XSS${NC}"
    echo ""
    echo -e "${CYAN}Commands:${NC}"
    echo -e "  ${BOLD}View logs:${NC}    $COMPOSE_CMD logs -f"
    echo -e "  ${BOLD}Stop:${NC}         $COMPOSE_CMD down"
    echo -e "  ${BOLD}Restart:${NC}      $COMPOSE_CMD restart"
    echo -e "  ${BOLD}Shell:${NC}        docker exec -it cybertron-tools bash"
    echo ""
    echo -e "${YELLOW}${BOLD}⚠ IMPORTANT:${NC} ${YELLOW}Add your NIM_API_KEY and HACKERONE_API_KEY to $CYBERTRON_DIR/.env${NC}"
    echo ""
}

# ─── Main ─────────────────────────────────────────────────────────────────────
main() {
    print_banner
    detect_os
    check_docker
    setup_directories
    setup_configs
    download_wordlists
    build_images
    start_services
    show_info
}

main "$@"
