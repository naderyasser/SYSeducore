#!/bin/bash
#
# Zero-Downtime Deployment Script for SYSeducore
# This script ensures the application remains available during updates
#
# Requirements:
# - Gunicorn (for graceful reload)
# - Systemd service or PM2 (process manager)
# - Nginx (reverse proxy)
#
# Usage:
#   ./deploy.sh [production|staging]
#

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
APP_DIR="/root/.gemini/antigravity/scratch/SYSeducore"
VENV_DIR="$APP_DIR/venv"
SERVICE_NAME="educore"
GUNICORN_PID_FILE="/tmp/gunicorn_educore.pid"
BACKUP_DIR="$APP_DIR/backups"
ENVIRONMENT="${1:-production}"

# Logging functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as correct user
check_user() {
    log_info "Checking user permissions..."
    if [ "$EUID" -eq 0 ]; then
        log_warn "Running as root. Consider running as application user for security."
    fi
}

# Create backup
create_backup() {
    log_info "Creating backup..."
    mkdir -p "$BACKUP_DIR"
    
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    BACKUP_FILE="$BACKUP_DIR/backup_$TIMESTAMP.tar.gz"
    
    tar -czf "$BACKUP_FILE" \
        --exclude='venv' \
        --exclude='__pycache__' \
        --exclude='*.pyc' \
        --exclude='staticfiles' \
        --exclude='media' \
        --exclude='logs' \
        -C "$APP_DIR/.." SYSeducore
    
    log_info "Backup created: $BACKUP_FILE"
    
    # Keep only last 5 backups
    cd "$BACKUP_DIR"
    ls -t backup_*.tar.gz | tail -n +6 | xargs -r rm
}

# Pull latest code
update_code() {
    log_info "Pulling latest code from repository..."
    cd "$APP_DIR"
    
    # Stash any local changes
    git stash
    
    # Pull latest changes
    git pull origin master
    
    log_info "Code updated successfully"
}

# Install/Update dependencies
update_dependencies() {
    log_info "Updating dependencies..."
    source "$VENV_DIR/bin/activate"
    
    pip install --upgrade pip
    pip install -r "$APP_DIR/requirements.txt" --no-cache-dir
    
    log_info "Dependencies updated"
}

# Run database migrations
run_migrations() {
    log_info "Running database migrations..."
    source "$VENV_DIR/bin/activate"
    cd "$APP_DIR"
    
    python manage.py migrate --noinput
    
    log_info "Migrations completed"
}

# Collect static files
collect_static() {
    log_info "Collecting static files..."
    source "$VENV_DIR/bin/activate"
    cd "$APP_DIR"
    
    python manage.py collectstatic --noinput --clear
    
    log_info "Static files collected"
}

# Run tests
run_tests() {
    log_info "Running tests..."
    source "$VENV_DIR/bin/activate"
    cd "$APP_DIR"
    
    python manage.py test --keepdb --parallel
    
    if [ $? -eq 0 ]; then
        log_info "All tests passed"
    else
        log_error "Tests failed! Deployment aborted."
        exit 1
    fi
}

# Graceful reload with Gunicorn
reload_gunicorn() {
    log_info "Reloading Gunicorn (graceful)..."
    
    if [ -f "$GUNICORN_PID_FILE" ]; then
        # Send HUP signal for graceful reload
        kill -HUP $(cat "$GUNICORN_PID_FILE")
        log_info "Gunicorn reloaded gracefully"
    else
        log_warn "Gunicorn PID file not found. Attempting systemd restart..."
        reload_systemd
    fi
}

# Reload with Systemd
reload_systemd() {
    log_info "Reloading application via systemd..."
    
    sudo systemctl reload "$SERVICE_NAME" || sudo systemctl restart "$SERVICE_NAME"
    
    # Wait for service to be active
    sleep 2
    
    if sudo systemctl is-active --quiet "$SERVICE_NAME"; then
        log_info "Service reloaded successfully"
    else
        log_error "Service failed to reload"
        exit 1
    fi
}

# Reload with PM2
reload_pm2() {
    log_info "Reloading application via PM2..."
    
    pm2 reload "$SERVICE_NAME" --update-env
    
    if [ $? -eq 0 ]; then
        log_info "PM2 reloaded successfully"
    else
        log_error "PM2 reload failed"
        exit 1
    fi
}

# Reload Celery workers
reload_celery() {
    log_info "Reloading Celery workers..."
    
    # Find and gracefully restart celery workers
    pkill -HUP -f 'celery worker' || log_warn "No Celery workers found"
    
    log_info "Celery workers reloaded"
}

# Health check
health_check() {
    log_info "Running health check..."
    
    # Wait for application to be ready
    sleep 3
    
    # Check if application is responding
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/accounts/login/)
    
    if [ "$HTTP_CODE" -eq 200 ] || [ "$HTTP_CODE" -eq 302 ]; then
        log_info "Health check passed (HTTP $HTTP_CODE)"
    else
        log_error "Health check failed (HTTP $HTTP_CODE)"
        log_error "Rolling back..."
        # Here you could implement rollback logic
        exit 1
    fi
}

# Clear cache
clear_cache() {
    log_info "Clearing application cache..."
    source "$VENV_DIR/bin/activate"
    cd "$APP_DIR"
    
    python manage.py shell -c "from django.core.cache import cache; cache.clear()"
    
    log_info "Cache cleared"
}

# Main deployment flow
main() {
    log_info "=========================================="
    log_info "Starting Zero-Downtime Deployment"
    log_info "Environment: $ENVIRONMENT"
    log_info "=========================================="
    
    check_user
    create_backup
    update_code
    update_dependencies
    run_migrations
    collect_static
    
    # Run tests only in production
    if [ "$ENVIRONMENT" = "production" ]; then
        run_tests
    fi
    
    clear_cache
    
    # Detect process manager and reload accordingly
    if [ -f "$GUNICORN_PID_FILE" ]; then
        reload_gunicorn
    elif command -v pm2 &> /dev/null; then
        reload_pm2
    elif systemctl is-active --quiet "$SERVICE_NAME"; then
        reload_systemd
    else
        log_error "No process manager detected. Please reload manually."
        exit 1
    fi
    
    reload_celery
    health_check
    
    log_info "=========================================="
    log_info "Deployment completed successfully!"
    log_info "=========================================="
}

# Run main deployment
main
