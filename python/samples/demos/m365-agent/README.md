# Microsoft Agent Framework Python Weather Agent sample (M365 Agents SDK)

This sample demonstrates a simple Weather Forecast Agent built with the Python Microsoft Agent Framework, exposed through the Microsoft 365 Agents SDK compatible endpoints. The agent accepts natural language requests for a weather forecast and responds with a textual answer. It supports multi-turn conversations to gather required information.

## Prerequisites

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) for fast dependency management
- [devtunnel](https://learn.microsoft.com/azure/developer/dev-tunnels/get-started?tabs=windows)
- [Microsoft 365 Agents Toolkit](https://github.com/OfficeDev/microsoft-365-agents-toolkit) for playground/testing
- Access to OpenAI or Azure OpenAI with a model like `gpt-4o-mini`

## Configuration

Set the following environment variables:

```bash
# Common
export PORT=3978
export USE_ANONYMOUS_MODE=True # set to false if using auth

# OpenAI
export OPENAI_API_KEY="..."
export OPENAI_CHAT_MODEL_ID="..."
```

## Installing Dependencies

From the repository root or the sample folder:

```bash
uv sync
```

## Running the Agent Locally

```bash
# Activate environment first if not already
source .venv/bin/activate   # (Windows PowerShell: .venv\Scripts\Activate.ps1)

# Run the weather agent demo
python m365_agent_demo/app.py
```

The agent starts on `http://localhost:3978`. Health check: `GET /api/health`.

## QuickStart using Agents Playground

1. Install (if not already):

   ```bash
   winget install agentsplayground
   ```

2. Start the Python agent locally: `python m365_agent_demo/app.py`
3. Start the playground: `agentsplayground`
4. Chat with the Weather Agent.

## QuickStart using WebChat (Azure Bot)

To test via WebChat you can provision an Azure Bot and point its messaging endpoint to your agent.

1. Create an Azure Bot (choose Client Secret auth for local tunneling).
2. Create a `.env` file in this sample folder with the following (replace placeholders):

   ```bash
   # Authentication / Agentic configuration
   USE_ANONYMOUS_MODE=False
   CONNECTIONS__SERVICE_CONNECTION__SETTINGS__CLIENTID="<client-id>"
   CONNECTIONS__SERVICE_CONNECTION__SETTINGS__CLIENTSECRET="<client-secret>"
   CONNECTIONS__SERVICE_CONNECTION__SETTINGS__TENANTID="<tenant-id>"
   CONNECTIONS__SERVICE_CONNECTION__SETTINGS__SCOPES=https://graph.microsoft.com/.default

   AGENTAPPLICATION__USERAUTHORIZATION__HANDLERS__AGENTIC__SETTINGS__TYPE=AgenticUserAuthorization
   AGENTAPPLICATION__USERAUTHORIZATION__HANDLERS__AGENTIC__SETTINGS__SCOPES=https://graph.microsoft.com/.default
   AGENTAPPLICATION__USERAUTHORIZATION__HANDLERS__AGENTIC__SETTINGS__ALTERNATEBLUEPRINTCONNECTIONNAME=https://graph.microsoft.com/.default
   ```

3. Host dev tunnel:

   ```bash
   devtunnel host -p 3978 --allow-anonymous
   ```

4. Set the bot Messaging endpoint to: `https://<tunnel-host>/api/messages`
5. Run your local agent: `python m365_agent_demo/app.py`
6. Use "Test in WebChat" in Azure Portal.

> Federated Credentials or Managed Identity auth types typically require deployment to Azure App Service instead of tunneling.

## Troubleshooting

- 404 on `/api/messages`: Ensure you are POSTing and using the correct tunnel URL.
- Empty responses: Check model key / quota and ensure environment variables are set.
- Auth errors when anonymous disabled: Validate MSAL config matches your Azure Bot registration.

## Further Reading

- [Microsoft 365 Agents SDK](https://learn.microsoft.com/microsoft-365/agents-sdk/)
- [Devtunnel docs](https://learn.microsoft.com/azure/developer/dev-tunnels/)
