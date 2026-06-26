# Microsoft Agent Framework Python Weather Agent sample (Teams SDK)

This sample demonstrates a simple Weather Forecast Agent built with the Python Microsoft Agent Framework, hosted as a Microsoft Teams bot through the [Teams SDK (teams.py)](https://github.com/microsoft/teams.py). The agent accepts natural language weather requests, streams its reply token-by-token into the chat, and remembers context across turns.

## Prerequisites

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) for fast dependency management
- [devtunnel](https://learn.microsoft.com/azure/developer/dev-tunnels/get-started?tabs=windows) for local testing
- A Microsoft Foundry project with a deployed model
- The [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) (run `az login` to authenticate)
- A Teams bot registration ([Azure Bot](https://learn.microsoft.com/azure/bot-service/abs-quickstart)) — App ID, password, and tenant

## Configuration

Create a `.env` file in this sample folder (see [.env.example](.env.example)):

```bash
# Microsoft Foundry (model the agent uses). Authenticate with `az login`.
FOUNDRY_PROJECT_ENDPOINT="https://<your-resource>.services.ai.azure.com/api/projects/<project-name>"
FOUNDRY_MODEL="<deployment-name>"

# Teams bot credentials
CLIENT_ID="<app-id>"
CLIENT_SECRET="<client-secret>"
TENANT_ID="<tenant-id>"

# Local hosting
PORT=3978
```

`FOUNDRY_MODEL` is the **deployment name** of your model, not the base model name.

## Running the Agent Locally

Authenticate with the Azure CLI, then start the app:

```bash
az login
uv run app.py
```

The bot starts an HTTP listener on `http://localhost:3978`; its messaging endpoint is `POST /api/messages`.

## Testing in Teams

To exchange messages with the bot from Teams, Teams needs to reach your local endpoint:

1. Create an Azure Bot (choose Client Secret auth for local tunneling) and copy its App ID, password, and tenant into `.env`. See [Create an Azure Bot resource](https://learn.microsoft.com/azure/bot-service/abs-quickstart) for step-by-step instructions.
2. Host a dev tunnel:

   ```bash
   devtunnel host -p 3978 --allow-anonymous
   ```

3. Set the bot's **Messaging endpoint** to `https://<tunnel-host>/api/messages`.
4. Run the agent: `uv run app.py`.
5. Register the bot as a Teams app and install it into a Teams chat, then message it, e.g. `What's the weather in Seattle?`. See [Register a Teams app in the Developer Portal](https://learn.microsoft.com/microsoftteams/platform/concepts/build-and-test/teams-developer-portal#register-an-app) for the manifest and sideloading steps.

## Troubleshooting

- **404 on `/api/messages`**: Ensure you are POSTing and using the correct tunnel URL.
- **Empty responses**: Check that `FOUNDRY_PROJECT_ENDPOINT` and `FOUNDRY_MODEL` are valid and that you have run `az login`.
- **Auth errors from Teams**: Validate `CLIENT_ID` / `CLIENT_SECRET` / `TENANT_ID` match your Azure Bot registration.

## Further Reading

- [Microsoft Teams SDK for Python (teams.py)](https://github.com/microsoft/teams.py)
- [Teams SDK for Python — Getting started](https://microsoft.github.io/teams-sdk/python/getting-started/)
- [Create an Azure Bot resource](https://learn.microsoft.com/azure/bot-service/abs-quickstart)
- [Register a Teams app in the Developer Portal](https://learn.microsoft.com/microsoftteams/platform/concepts/build-and-test/teams-developer-portal#register-an-app)
- [Devtunnel docs](https://learn.microsoft.com/azure/developer/dev-tunnels/)
