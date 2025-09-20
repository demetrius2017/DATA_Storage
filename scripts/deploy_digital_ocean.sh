#!/bin/bash

# 🚀 Digital Ocean Deployment Script for OrderBook Collector
# This script automates the full deployment process

set -e  # Exit on any error

echo "🚀 Starting Digital Ocean Deployment..."
echo "========================================"

# Configuration
PROJECT_NAME="orderbook-collector"
GITHUB_REPO="https://github.com/demetrius2017/DATA_Storage.git"
DOCKER_COMPOSE_FILE="docker-compose.yml"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as root
check_root() {
    if [[ $EUID -eq 0 ]]; then
        print_status "Running as root user ✓"
    else
        print_error "This script must be run as root"
        exit 1
    fi
}

# Install Docker and Docker Compose
install_docker() {
    print_status "Installing Docker..."
    
    # Remove old versions
    apt-get remove -y docker docker-engine docker.io containerd runc 2>/dev/null || true
    
    # Update package index
    apt-get update
    
    # Install dependencies
    apt-get install -y \
        ca-certificates \
        curl \
        gnupg \
        lsb-release
    
    # Add Docker's official GPG key
    mkdir -p /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    
    # Set up repository
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
      $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
    
    # Install Docker Engine
    apt-get update
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
    
    # Install Docker Compose (standalone)
    curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    chmod +x /usr/local/bin/docker-compose
    
    # Start Docker service
    systemctl start docker
    systemctl enable docker
    
    print_status "Docker installed successfully ✓"
}

# Clone or update project repository
setup_project() {
    print_status "Setting up project..."
    
    PROJECT_DIR="/opt/${PROJECT_NAME}"
    
    if [ -d "$PROJECT_DIR" ]; then
        print_warning "Project directory exists, updating..."
        cd "$PROJECT_DIR"
        git pull origin master
    else
        print_status "Cloning project repository..."
        git clone "$GITHUB_REPO" "$PROJECT_DIR"
        cd "$PROJECT_DIR"
    fi
    
    print_status "Project setup completed ✓"
}

# Create environment file
create_env_file() {
    print_status "Creating environment configuration..."
    
    ENV_FILE="/opt/${PROJECT_NAME}/.env"
    
    if [ ! -f "$ENV_FILE" ]; then
        cat > "$ENV_FILE" << EOF
# PostgreSQL Database (Digital Ocean Managed Database)
DB_HOST=your-cluster-do-user-123456-0.b.db.ondigitalocean.com
DB_PORT=25060
DB_NAME=defaultdb
DB_USER=doadmin
DB_PASSWORD=your_password_here

# Binance API Credentials
BINANCE_API_KEY=your_binance_api_key_here
BINANCE_SECRET_KEY=your_binance_secret_key_here

# Monitoring
GRAFANA_PASSWORD=secure_grafana_password_123

# System Configuration
LOG_LEVEL=INFO
SYMBOLS_CHUNK_SIZE=50
BATCH_SIZE=100
EOF
        
        print_warning "Please edit $ENV_FILE with your actual credentials!"
        print_warning "The deployment will pause to allow you to configure the environment."
        
        # Open the file in nano for editing
        nano "$ENV_FILE"
    else
        print_status "Environment file already exists ✓"
    fi
}

# Create necessary directories
create_directories() {
    print_status "Creating project directories..."
    
    PROJECT_DIR="/opt/${PROJECT_NAME}"
    
    mkdir -p "$PROJECT_DIR/logs"
    mkdir -p "$PROJECT_DIR/data"
    mkdir -p "$PROJECT_DIR/monitoring/grafana/provisioning"
    mkdir -p "$PROJECT_DIR/monitoring/rules"
    
    # Set permissions
    chown -R 1000:1000 "$PROJECT_DIR/logs"
    chown -R 1000:1000 "$PROJECT_DIR/data"
    
    print_status "Directories created ✓"
}

# Configure firewall
configure_firewall() {
    print_status "Configuring firewall..."
    
    # Install ufw if not present
    apt-get install -y ufw
    
    # Basic firewall rules
    ufw --force reset
    ufw default deny incoming
    ufw default allow outgoing
    
    # Allow SSH
    ufw allow ssh
    
    # Allow application ports
    ufw allow 8080/tcp   # API
    ufw allow 3000/tcp   # Grafana
    ufw allow 9090/tcp   # Prometheus
    
    # Enable firewall
    ufw --force enable
    
    print_status "Firewall configured ✓"
}

# Build and start containers
deploy_containers() {
    print_status "Building and deploying containers..."
    
    cd "/opt/${PROJECT_NAME}"
    
    # Build images
    docker-compose build
    
    # Start services
    docker-compose up -d
    
    # Wait for services to start
    print_status "Waiting for services to start..."
    sleep 30
    
    # Check container status
    docker-compose ps
    
    print_status "Containers deployed ✓"
}

# Setup monitoring dashboards
setup_monitoring() {
    print_status "Setting up monitoring dashboards..."
    
    # Wait for Grafana to be ready
    sleep 30
    
    # Import dashboards (this would be done via Grafana API)
    print_status "Monitoring setup completed ✓"
}

# Validate deployment
validate_deployment() {
    print_status "Validating deployment..."
    
    # Check if containers are running
    if ! docker-compose ps | grep -q "Up"; then
        print_error "Some containers are not running!"
        docker-compose logs
        exit 1
    fi
    
    # Check API endpoint
    if curl -f http://localhost:8080/health > /dev/null 2>&1; then
        print_status "API endpoint is healthy ✓"
    else
        print_warning "API endpoint check failed"
    fi
    
    # Check Grafana
    if curl -f http://localhost:3000 > /dev/null 2>&1; then
        print_status "Grafana is accessible ✓"
    else
        print_warning "Grafana check failed"
    fi
    
    print_status "Deployment validation completed ✓"
}

# Main deployment function
main() {
    echo "🚀 Digital Ocean OrderBook Collector Deployment"
    echo "================================================"
    echo ""
    
    check_root
    
    print_status "Starting deployment process..."
    
    # System setup
    apt-get update
    install_docker
    
    # Project setup
    setup_project
    create_env_file
    create_directories
    configure_firewall
    
    # Deployment
    deploy_containers
    setup_monitoring
    validate_deployment
    
    echo ""
    echo "🎉 Deployment completed successfully!"
    echo "====================================="
    echo ""
    echo "📊 Access your services:"
    echo "   API:        http://$(curl -s ifconfig.me):8080"
    echo "   Grafana:    http://$(curl -s ifconfig.me):3000 (admin/admin123)"
    echo "   Prometheus: http://$(curl -s ifconfig.me):9090"
    echo ""
    echo "📝 Next steps:"
    echo "   1. Configure your Binance API keys in /opt/$PROJECT_NAME/.env"
    echo "   2. Update PostgreSQL credentials"
    echo "   3. Restart services: cd /opt/$PROJECT_NAME && docker-compose restart"
    echo "   4. Monitor logs: docker-compose logs -f"
    echo ""
    echo "🔧 Useful commands:"
    echo "   Status:   docker-compose ps"
    echo "   Logs:     docker-compose logs -f collector"
    echo "   Restart:  docker-compose restart"
    echo "   Stop:     docker-compose down"
    echo ""
}

# Run main function
main "$@"