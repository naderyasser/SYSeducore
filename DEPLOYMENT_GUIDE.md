# Zero-Downtime Deployment Guide for SYSeducore

This guide provides multiple deployment strategies for updating the SYSeducore application with zero downtime.

## Prerequisites

- Nginx configured as reverse proxy
- One of the following process managers:
  - **PM2** (Recommended)
  - **Systemd**
  - **Gunicorn with PID file**

## Quick Deployment

### Using the Automated Script

```bash
# Make script executable (first time only)
chmod +x deploy.sh

# Run deployment
./deploy.sh production
```

The script will:
1. Create a backup
2. Pull latest code
3. Update dependencies
4. Run migrations
5. Collect static files
6. Run tests
7. Gracefully reload the application
8. Perform health checks

## Method 1: PM2 (Recommended)

PM2 provides the best zero-downtime deployment experience.

### Initial Setup

```bash
# Install PM2 globally
npm install -g pm2

# Start application
pm2 start ecosystem.config.js

# Save PM2 configuration
pm2 save

# Setup PM2 to start on boot
pm2 startup
```

### Deploy Updates

```bash
# Pull latest code
git pull origin master

# Install dependencies
source venv/bin/activate
pip install -r requirements.txt

# Run migrations
python manage.py migrate

# Collect static files
python manage.py collectstatic --noinput

# Reload with zero downtime
pm2 reload educore-web --update-env
pm2 reload educore-celery-worker
pm2 reload educore-celery-beat
```

### PM2 Commands

```bash
# Check status
pm2 status

# View logs
pm2 logs educore-web

# Monitor resources
pm2 monit

# Restart (with downtime)
pm2 restart educore-web

# Stop application
pm2 stop all
```

## Method 2: Systemd

Systemd provides native service management on Linux.

### Initial Setup

```bash
# Copy service files to systemd directory
sudo cp educore.service /etc/systemd/system/
sudo cp educore-celery-worker.service /etc/systemd/system/
sudo cp educore-celery-beat.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable services to start on boot
sudo systemctl enable educore
sudo systemctl enable educore-celery-worker
sudo systemctl enable educore-celery-beat

# Start services
sudo systemctl start educore
sudo systemctl start educore-celery-worker
sudo systemctl start educore-celery-beat
```

### Deploy Updates

```bash
# Pull latest code
git pull origin master

# Install dependencies
source venv/bin/activate
pip install -r requirements.txt

# Run migrations
python manage.py migrate

# Collect static files
python manage.py collectstatic --noinput

# Graceful reload (zero downtime)
sudo systemctl reload educore

# Or restart with minimal downtime
sudo systemctl restart educore
sudo systemctl restart educore-celery-worker
sudo systemctl restart educore-celery-beat
```

### Systemd Commands

```bash
# Check status
sudo systemctl status educore

# View logs
sudo journalctl -u educore -f

# Stop service
sudo systemctl stop educore
```

## Method 3: Manual Gunicorn Reload

If using Gunicorn directly without a process manager.

### Start Gunicorn

```bash
cd /root/.gemini/antigravity/scratch/SYSeducore
source venv/bin/activate

gunicorn config.wsgi:application \
    --bind 0.0.0.0:3000 \
    --workers 4 \
    --daemon \
    --pid /tmp/gunicorn_educore.pid \
    --access-logfile logs/access.log \
    --error-logfile logs/error.log
```

### Deploy Updates

```bash
# Pull and prepare
git pull origin master
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput

# Graceful reload
kill -HUP $(cat /tmp/gunicorn_educore.pid)
```

## Method 4: Blue-Green Deployment

For maximum safety with instant rollback capability.

### Setup

1. Run two identical environments (blue and green)
2. Nginx routes traffic to the active environment
3. Update the inactive environment
4. Switch Nginx to route to updated environment
5. Keep old environment as backup for rollback

### Nginx Configuration

```nginx
upstream blue {
    server localhost:3000;
}

upstream green {
    server localhost:3001;
}

upstream active {
    server localhost:3000;  # Change this to switch
}

server {
    listen 80;
    server_name sys.educore.software;

    location / {
        proxy_pass http://active;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## Health Checks

Always verify deployment success:

```bash
# Check HTTP status
curl -I http://localhost:3000/accounts/login/

# Check application logs
tail -f logs/django.log

# Check error logs
tail -f logs/errors.log

# Test critical endpoints
curl http://localhost:3000/api/stats/
```

## Rollback Strategy

If deployment fails:

### Using Backup

```bash
# Stop application
pm2 stop all  # or: sudo systemctl stop educore

# Restore from backup
cd /root/.gemini/antigravity/scratch
tar -xzf SYSeducore/backups/backup_YYYYMMDD_HHMMSS.tar.gz

# Restart application
pm2 start all  # or: sudo systemctl start educore
```

### Using Git

```bash
# Revert to previous commit
git revert HEAD
git push origin master

# Redeploy
./deploy.sh production
```

## Monitoring

### Application Monitoring

```bash
# PM2 monitoring
pm2 monit

# System resources
htop

# Check port 3000
netstat -tlnp | grep 3000

# Check process
ps aux | grep gunicorn
```

### Log Monitoring

```bash
# Real-time logs
tail -f logs/django.log
tail -f logs/errors.log
tail -f logs/access.log

# Celery logs
tail -f logs/celery_worker.log
tail -f logs/celery_beat.log
```

## Best Practices

1. **Always test locally first**
2. **Create backups before deployment**
3. **Run tests before deploying to production**
4. **Monitor logs during deployment**
5. **Keep rollback plan ready**
6. **Use version tags in git**
7. **Schedule deployments during low-traffic periods**
8. **Notify team before deployment**

## Troubleshooting

### Port 3000 already in use

```bash
# Find process using port 3000
lsof -i :3000

# Kill process if needed
kill -9 <PID>
```

### Permission errors

```bash
# Fix file permissions
chmod -R 755 /root/.gemini/antigravity/scratch/SYSeducore
chown -R root:root /root/.gemini/antigravity/scratch/SYSeducore
```

### Database migration errors

```bash
# Check migration status
python manage.py showmigrations

# Fake migration if needed
python manage.py migrate --fake <app> <migration>
```

### Static files not updating

```bash
# Clear static files and recollect
rm -rf staticfiles/*
python manage.py collectstatic --noinput --clear
```

## Security Notes

- Always use HTTPS in production
- Keep SECRET_KEY secure and never commit it
- Regularly update dependencies
- Monitor security logs
- Use firewall rules to restrict access
- Keep backups encrypted
- Rotate database passwords regularly

## Support

For issues or questions, contact the development team or refer to the project documentation.
