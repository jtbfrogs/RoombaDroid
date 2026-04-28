#!/bin/bash
# Run tests for DROID system

echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║              DROID SYSTEM - Test Suite                     ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# Activate venv
if [ -d "droid_env" ]; then
    source droid_env/bin/activate
else
    echo "Virtual environment not found. Run run.sh first."
    exit 1
fi

# Run tests
python3 test_system.py
