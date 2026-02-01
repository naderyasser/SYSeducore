# PM2 Ecosystem Configuration for SYSeducore
# This configuration enables zero - downtime deployments with PM2

module.exports = {
    apps: [
        {
            name: 'educore-web',
            script: 'gunicorn',
            args: 'config.wsgi:application --bind 0.0.0.0:3000 --workers 4 --timeout 120 --access-logfile logs/access.log --error-logfile logs/error.log',
            cwd: '/root/.gemini/antigravity/scratch/SYSeducore',
            interpreter: 'venv/bin/python',
            instances: 1,
            exec_mode: 'fork',
            autorestart: true,
            watch: false,
            max_memory_restart: '500M',
            env: {
                DJANGO_SETTINGS_MODULE: 'config.settings',
                PYTHONUNBUFFERED: '1'
            },
            error_file: 'logs/pm2-error.log',
            out_file: 'logs/pm2-out.log',
            log_date_format: 'YYYY-MM-DD HH:mm:ss Z'
        },
        {
            name: 'educore-celery-worker',
            script: 'venv/bin/celery',
            args: '-A config worker --loglevel=info --concurrency=2',
            cwd: '/root/.gemini/antigravity/scratch/SYSeducore',
            interpreter: 'venv/bin/python',
            instances: 1,
            exec_mode: 'fork',
            autorestart: true,
            watch: false,
            max_memory_restart: '300M',
            env: {
                DJANGO_SETTINGS_MODULE: 'config.settings',
                PYTHONUNBUFFERED: '1'
            }
        },
        {
            name: 'educore-celery-beat',
            script: 'venv/bin/celery',
            args: '-A config beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler',
            cwd: '/root/.gemini/antigravity/scratch/SYSeducore',
            interpreter: 'venv/bin/python',
            instances: 1,
            exec_mode: 'fork',
            autorestart: true,
            watch: false,
            env: {
                DJANGO_SETTINGS_MODULE: 'config.settings',
                PYTHONUNBUFFERED: '1'
            }
        }
    ]
}
