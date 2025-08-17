#!/bin/bash
# 5G NR SSB Signal Scanner - Startup Script

echo "5G NR SSB Signal Scanner"
echo "========================"

# Initialize variables
USE_SYSTEM_PYTHON=0

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    if [ $? -ne 0 ]; then
        echo "Failed to create virtual environment. Using system Python..."
        USE_SYSTEM_PYTHON=1
    fi
fi

# Activate virtual environment if it exists and works
if [ -d "venv" ] && [ "$USE_SYSTEM_PYTHON" -eq 0 ]; then
    if [ -f "venv/bin/activate" ]; then
        echo "Activating virtual environment..."
        source venv/bin/activate
        PIP_CMD="pip"
        PYTHON_CMD="python"
    else
        echo "Virtual environment corrupt. Using system Python..."
        USE_SYSTEM_PYTHON=1
    fi
fi

# Set commands for system Python if needed
if [ "$USE_SYSTEM_PYTHON" -eq 1 ]; then
    echo "Using system Python installation..."
    PIP_CMD="pip3"
    PYTHON_CMD="python3"
fi

# Install requirements
echo "Installing dependencies..."
$PIP_CMD install -r requirements.txt

# Create data directory if it doesn't exist
mkdir -p data

# Start the application
echo ""
echo "Starting application..."
echo "Access the web interface at: http://localhost:5000"
echo "Press Ctrl+C to stop"
echo ""

$PYTHON_CMD app.py