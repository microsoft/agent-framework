# Testing DevUI - Quick Setup Guide

Hi everyone! Here are the step-by-step instructions to test the new DevUI feature:

## 1. Get the Code

```bash
git pull
git checkout victordibia/devui
```

## 2. Setup Environment

Navigate to the Python directory and install dependencies:

```bash
cd python
uv sync --dev
source .venv/bin/activate
```

## 3. Configure Environment Variables

Create a `.env` file in the `python/` directory with your API credentials:

```bash
# Copy the example file
cp .env.example .env
```

Then edit `.env` and add your API keys:

```bash
# For OpenAI (minimum required)
OPENAI_API_KEY="your-api-key-here"
OPENAI_CHAT_MODEL_ID="gpt-4o-mini"

# Or for Azure OpenAI
AZURE_OPENAI_ENDPOINT="your-endpoint"
AZURE_OPENAI_CHAT_DEPLOYMENT_NAME="your-deployment-name"
```

## 4. Test DevUI

**Option A: In-Memory Mode (Recommended for quick testing)**

```bash
cd packages/devui/samples
python in_memory_mode.py
```

This runs a simple example with predefined agents and opens your browser automatically at http://localhost:8090

**Option B: Directory-Based Discovery**

```bash
cd packages/devui/samples
devui
```

This launches the UI with all example agents/workflows at http://localhost:8080

## 5. What You'll See

- A web interface for testing agents interactively
- Multiple example agents (weather assistant, general assistant, etc.)
- OpenAI-compatible API endpoints for programmatic access

## 6. API Testing (Optional)

You can also test via API calls:

```bash
curl -X POST http://localhost:8080/v1/responses \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agent-framework",
    "input": "What is the weather in Seattle?",
    "extra_body": {"entity_id": "weather_agent"}
  }'
```

## Troubleshooting

- **Missing API key**: Make sure your `.env` file is in the `python/` directory with valid credentials
- **Import errors**: Run `uv sync --dev` again to ensure all dependencies are installed
- **Port conflicts**: DevUI uses ports 8080 and 8090 by default - close other services using these ports

Let me know if you run into any issues!
