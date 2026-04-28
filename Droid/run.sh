#!/bin/bash
# Start the DROID system v3.0

echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║              DROID SYSTEM v3.0 - Starting                  ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# Check if venv exists
if [ ! -d "droid_env" ]; then
    echo "Creating virtual environment..."
    python3 -m venv droid_env
fi

# Activate venv
source droid_env/bin/activate

# Install requirements
pip install -q -r requirements.txt

# Run main program
python3 main.py
