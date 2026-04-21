# Foundry Hosted Agents Samples

This directory contains samples that demonstrate how to use the Agent Framework to host agents on Foundry with different capabilities and configurations. Each sample includes a README with instructions on how to set up, run, and interact with the agent.

Read more about Foundry Hosted Agents [here](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents).

## Environment setup

1. Navigate to the sample directory you want to run. For example:

   ```bash
   python -m venv .venv

   # Windows
   .venv\Scripts\Activate

   # macOS/Linux
   source .venv/bin/activate
   ```

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Create a `.env` file with your Foundry configuration following the `env.example` file in the sample.

4. Make sure you are logged in with the Azure CLI:

   ```bash
   az login
   ```

## Deploying to a Docker container

Navigate to the sample directory and build the Docker image:

```bash
docker build -t hosted-agent-sample .
```

Run the container, passing in the required environment variables:

```bash
docker run -p 8088:8088 \
  -e FOUNDRY_PROJECT_ENDPOINT=<your-endpoint> \
  -e MODEL_DEPLOYMENT_NAME=<your-model> \
  hosted-agent-sample
```

The server will be available at `http://localhost:8088`. You can send requests using the same `curl` command shown above.

## Deploying to Foundry

Follow this [guide](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent?tabs=bash#configure-your-agent) to deploy your agent to Foundry.
