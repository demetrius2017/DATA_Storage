#!/bin/bash

# 🎛️ OrderBook Collector Management Script
# Управление развертыванием и мониторингом на Digital Ocean

set -e

# Configuration
PROJECT_NAME="orderbook-collector"
REMOTE_HOST=""
REMOTE_USER="root"
SSH_KEY=""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_header() {
    echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║                OrderBook Collector Manager                   ║${NC}"
    echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Load configuration
load_config() {
    CONFIG_FILE="./config/deploy.conf"
    
    if [ -f "$CONFIG_FILE" ]; then
        source "$CONFIG_FILE"
        print_status "Configuration loaded from $CONFIG_FILE"
    else
        print_warning "Configuration file not found. Creating default..."
        create_config
    fi
}

# Create configuration file
create_config() {
    mkdir -p ./config
    
    cat > ./config/deploy.conf << 'EOF'
# Digital Ocean Deployment Configuration

# Server Details
REMOTE_HOST="your.droplet.ip.address"
REMOTE_USER="root"
SSH_KEY="~/.ssh/id_rsa"

# Database Configuration
DB_HOST="your-cluster-do-user-123456-0.b.db.ondigitalocean.com"
DB_PORT="25060"
DB_NAME="defaultdb"
DB_USER="doadmin"
DB_PASSWORD="your_password_here"

# API Keys
BINANCE_API_KEY="your_binance_api_key"
BINANCE_SECRET_KEY="your_binance_secret_key"

# Monitoring
GRAFANA_PASSWORD="secure_password_123"

# Project Settings
SYMBOLS_TO_COLLECT="BTCUSDT,ETHUSDT,SOLUSDT"  # Start with 3 symbols
LOG_LEVEL="INFO"
BATCH_SIZE="100"
EOF
    
    print_warning "Please edit ./config/deploy.conf with your actual values!"
    exit 1
}

# SSH connection helper
ssh_exec() {
    ssh -i "$SSH_KEY" "$REMOTE_USER@$REMOTE_HOST" "$1"
}

scp_upload() {
    scp -i "$SSH_KEY" "$1" "$REMOTE_USER@$REMOTE_HOST:$2"
}

# Deploy to Digital Ocean
deploy() {
    print_status "🚀 Starting deployment to Digital Ocean..."
    
    if [ -z "$REMOTE_HOST" ]; then
        print_error "REMOTE_HOST not configured. Please edit ./config/deploy.conf"
        exit 1
    fi
    
    # Test SSH connection
    print_status "Testing SSH connection..."
    if ! ssh_exec "echo 'SSH connection successful'"; then
        print_error "SSH connection failed. Check your configuration."
        exit 1
    fi
    
    # Upload deployment script
    print_status "Uploading deployment script..."
    scp_upload "./scripts/deploy_digital_ocean.sh" "/tmp/deploy.sh"
    
    # Make script executable and run
    print_status "Executing deployment script on remote server..."
    ssh_exec "chmod +x /tmp/deploy.sh && /tmp/deploy.sh"
    
    print_status "✅ Deployment completed!"
}

# Update environment configuration
update_config() {
    print_status "🔧 Updating remote configuration..."
    
    # Create temporary .env file
    TEMP_ENV="/tmp/orderbook_collector.env"
    
    cat > "$TEMP_ENV" << EOF
# PostgreSQL Database
DB_HOST=$DB_HOST
DB_PORT=$DB_PORT
DB_NAME=$DB_NAME
DB_USER=$DB_USER
DB_PASSWORD=$DB_PASSWORD

# Binance API
BINANCE_API_KEY=$BINANCE_API_KEY
BINANCE_SECRET_KEY=$BINANCE_SECRET_KEY

# Monitoring
GRAFANA_PASSWORD=$GRAFANA_PASSWORD

# System Configuration
LOG_LEVEL=$LOG_LEVEL
SYMBOLS_CHUNK_SIZE=50
BATCH_SIZE=$BATCH_SIZE
EOF
    
    # Upload configuration
    scp_upload "$TEMP_ENV" "/opt/$PROJECT_NAME/.env"
    
    # Restart services
    ssh_exec "cd /opt/$PROJECT_NAME && docker-compose restart"
    
    # Cleanup
    rm "$TEMP_ENV"
    
    print_status "✅ Configuration updated and services restarted!"
}

# Check status
status() {
    print_status "📊 Checking system status..."
    
    echo -e "\n${BLUE}=== Container Status ===${NC}"
    ssh_exec "cd /opt/$PROJECT_NAME && docker-compose ps"
    
    echo -e "\n${BLUE}=== System Resources ===${NC}"
    ssh_exec "free -h && df -h"
    
    echo -e "\n${BLUE}=== Recent Logs ===${NC}"
    ssh_exec "cd /opt/$PROJECT_NAME && docker-compose logs --tail=20 collector"
}

# Show logs
logs() {
    local service=${1:-collector}
    print_status "📝 Showing logs for service: $service"
    
    ssh_exec "cd /opt/$PROJECT_NAME && docker-compose logs -f $service"
}

# Scale symbols
scale() {
    local symbol_count=${1:-50}
    print_status "📈 Scaling to $symbol_count symbols..."
    
    # Get top symbols list
    python3 << EOF
import sys
sys.path.append('.')
from collector.config.symbols import TOP_200_SYMBOLS

# Get first N symbols
symbols = TOP_200_SYMBOLS[:$symbol_count]
symbols_str = ','.join(symbols)
print(symbols_str)
EOF
}

# Backup data
backup() {
    print_status "💾 Creating data backup..."
    
    local backup_date=$(date +%Y%m%d_%H%M%S)
    local backup_dir="./backups/$backup_date"
    
    mkdir -p "$backup_dir"
    
    # Backup database
    ssh_exec "cd /opt/$PROJECT_NAME && docker-compose exec postgres pg_dump -U \$DB_USER \$DB_NAME" > "$backup_dir/database.sql"
    
    # Backup configuration
    scp_upload "$REMOTE_USER@$REMOTE_HOST:/opt/$PROJECT_NAME/.env" "$backup_dir/"
    
    print_status "✅ Backup created in $backup_dir"
}

# Monitor performance
monitor() {
    print_status "📈 Opening monitoring dashboard..."
    
    local grafana_url="http://$REMOTE_HOST:3000"
    
    if command -v open &> /dev/null; then
        open "$grafana_url"
    elif command -v xdg-open &> /dev/null; then
        xdg-open "$grafana_url"
    else
        print_status "Open manually: $grafana_url"
    fi
}

# Stop services
stop() {
    print_status "🛑 Stopping services..."
    ssh_exec "cd /opt/$PROJECT_NAME && docker-compose down"
    print_status "✅ Services stopped!"
}

# Start services
start() {
    print_status "▶️ Starting services..."
    ssh_exec "cd /opt/$PROJECT_NAME && docker-compose up -d"
    print_status "✅ Services started!"
}

# Restart services
restart() {
    print_status "🔄 Restarting services..."
    ssh_exec "cd /opt/$PROJECT_NAME && docker-compose restart"
    print_status "✅ Services restarted!"
}

# Show help
show_help() {
    echo "OrderBook Collector Management Commands:"
    echo ""
    echo "Deployment:"
    echo "  deploy          Deploy to Digital Ocean"
    echo "  update-config   Update remote configuration"
    echo ""
    echo "Management:"
    echo "  status          Show system status"
    echo "  logs [service]  Show logs (default: collector)"
    echo "  start           Start all services"
    echo "  stop            Stop all services"
    echo "  restart         Restart all services"
    echo ""
    echo "Scaling:"
    echo "  scale [count]   Scale to N symbols (default: 50)"
    echo ""
    echo "Monitoring:"
    echo "  monitor         Open Grafana dashboard"
    echo "  backup          Create data backup"
    echo ""
    echo "Examples:"
    echo "  ./manage.sh deploy"
    echo "  ./manage.sh status"
    echo "  ./manage.sh logs collector"
    echo "  ./manage.sh scale 100"
    echo ""
}

# Main function
main() {
    print_header
    
    load_config
    
    case "${1:-help}" in
        deploy)
            deploy
            ;;
        update-config)
            update_config
            ;;
        status)
            status
            ;;
        logs)
            logs "$2"
            ;;
        scale)
            scale "$2"
            ;;
        backup)
            backup
            ;;
        monitor)
            monitor
            ;;
        start)
            start
            ;;
        stop)
            stop
            ;;
        restart)
            restart
            ;;
        help|--help|-h)
            show_help
            ;;
        *)
            print_error "Unknown command: $1"
            echo ""
            show_help
            exit 1
            ;;
    esac
}

# Run main function
main "$@"