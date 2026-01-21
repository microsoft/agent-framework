# Sample Integration Tests

Integration tests that validate the Durable Agent Framework samples by running them against a Durable Task Scheduler (DTS) instance.

## Setup

### 1. Create `.env` file

Copy `.env.example` to `.env` and fill in your Azure credentials:

```bash
cp .env.example .env
```

Required variables:
- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME`
- `AZURE_OPENAI_API_KEY` (optional if using Azure CLI authentication)
- `RUN_INTEGRATION_TESTS` (set to `true`)
- `ENDPOINT` (default: http://localhost:8080)
- `TASKHUB` (default: default)

Optional variables (for streaming tests):
- `REDIS_CONNECTION_STRING` (default: redis://localhost:6379)
- `REDIS_STREAM_TTL_MINUTES` (default: 10)

### 2. Start required services

**Durable Task Scheduler:**
```bash
docker run -d --name dts-emulator -p 8080:8080 -p 8082:8082 mcr.microsoft.com/dts/dts-emulator:latest
```
- Port 8080: gRPC endpoint (used by tests)
- Port 8082: Web dashboard (optional, for monitoring)

**Redis (for streaming tests):**
```bash
docker run -d --name redis -p 6379:6379 redis:latest
```
- Port 6379: Redis server endpoint

## Running Tests

The tests automatically start and stop worker processes for each sample.

### Run all sample tests
```bash
uv run pytest packages/durabletask/tests/integration_tests -v
```

### Run specific sample
```bash
uv run pytest packages/durabletask/tests/integration_tests/test_01_single_agent.py -v
```

### Run with verbose output
```bash
uv run pytest packages/durabletask/tests/integration_tests -sv
```

## How It Works

Each test file uses pytest markers to automatically configure and start the worker process:

```python
pytestmark = [
    pytest.mark.sample("03_single_agent_streaming"),
    pytest.mark.integration_test,
    pytest.mark.requires_azure_openai,
    pytest.mark.requires_dts,
    pytest.mark.requires_redis,
]
```

## Troubleshooting

**Tests are skipped:**
Ensure `RUN_INTEGRATION_TESTS=true` is set in your `.env` file.

**DTS connection failed:**
Check that the DTS emulator container is running: `docker ps | grep dts-emulator`

**Redis connection failed:**
Check that Redis is running: `docker ps | grep redis`

**Missing environment variables:**
Ensure your `.env` file contains all required variables from `.env.example`.

**Tests timeout:**
Check that Azure OpenAI credentials are valid and the service is accessible.

If you see "DTS emulator is not available":
- Ensure Docker container is running: `docker ps | grep dts-emulator`
- Check port 8080 is not in use by another process
- Restart the container if needed

### Azure OpenAI Errors

If you see authentication or deployment errors:
- Verify your `AZURE_OPENAI_ENDPOINT` is correct
- Confirm `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME` matches your deployment
- If using API key, check `AZURE_OPENAI_API_KEY` is valid
- If using Azure CLI, ensure you're logged in: `az login`

## CI/CD

For automated testing in CI/CD pipelines:

1. Use Docker Compose to start DTS emulator
2. Set environment variables via CI/CD secrets
3. Run tests with appropriate markers: `pytest -m integration_test`
