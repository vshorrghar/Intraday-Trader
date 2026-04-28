#!/bin/bash

# Wealth Manager Pro - Web App Launcher
# Simple script to start the web application

echo "🚀 Starting Wealth Manager Pro Web Application"
echo ""

# Check if we're in the right directory
if [ ! -f "webapp/app.py" ]; then
    echo "❌ Error: Please run this script from the w-builder directory"
    echo "   cd ~/kiro/websites/w-builder && ./start_webapp.sh"
    exit 1
fi

# Check if AWS credentials are set
if [ -z "$AWS_ACCESS_KEY_ID" ]; then
    echo "⚠️  WARNING: AWS credentials not found!"
    echo ""
    echo "Please set your AWS credentials first:"
    echo ""
    echo "  export AWS_ACCESS_KEY_ID=\"...\""
    echo "  export AWS_SECRET_ACCESS_KEY=\"...\""
    echo "  export AWS_SESSION_TOKEN=\"...\""
    echo ""
    read -p "Continue anyway? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
else
    echo "✅ AWS credentials detected"
    # Test credentials
    aws sts get-caller-identity &>/dev/null
    if [ $? -eq 0 ]; then
        echo "✅ AWS credentials valid"
    else
        echo "⚠️  AWS credentials may be expired - run 'aws sts get-caller-identity' to verify"
    fi
fi

echo ""
echo "📂 Starting Flask server..."
echo "   🌐 Access at: http://localhost:8080"
echo ""
echo "Press Ctrl+C to stop the server"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Start the Flask app
python3 webapp/app.py
