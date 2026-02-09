#!/bin/bash
# Development Server Start Script
# This script starts the Django development server with auto-reload on port 3000

echo "🚀 Starting Django Development Server on port 3000..."
echo "📁 Project: SYSeducore"
echo "🔄 Auto-reload: ENABLED"
echo ""

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    echo "✅ Activating virtual environment..."
    source venv/bin/activate
fi

# Run migrations
echo "🔧 Applying database migrations..."
python manage.py migrate --no-input

# Collect static files (optional in dev)
# python manage.py collectstatic --no-input --clear

# Start development server
echo "🌐 Starting server at http://localhost:3000"
echo "⚡ Press CTRL+C to stop the server"
echo "═══════════════════════════════════════════════════"
echo ""

python manage.py runserver 0.0.0.0:3000
