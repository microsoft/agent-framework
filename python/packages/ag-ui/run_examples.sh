#!/usr/bin/env bash

set -e  # Exit on any error

echo "Checking for processes on port 8000..."

# Find and kill the process on port 8000
if lsof -i :8000 > /dev/null 2>&1; then
  echo "Found process on port 8000. Killing it..."
  lsof -ti:8000 | xargs kill -9 2>/dev/null || true
  echo "Process killed."
else
  echo "No process found on port 8000."
fi

# Wait a moment for the port to be released
sleep 2

echo "Starting agent framework AG-UI examples on port 8000..."

# Start the server
UVICORN_HOST=0.0.0.0 UVICORN_PORT=8000 python -m agent_framework_ag_ui_examples