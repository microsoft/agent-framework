# Auth Client-Server Sample

This sample demonstrates how to authorize AI agents and their tools using OAuth 2.0 scopes. It shows two levels of access control: an endpoint-level scope (`agent.chat`) that gates access to the agent, and tool-level scopes (`expenses.view`, `expenses.approve`) that control what the agent can do on behalf of each user.

While this sample uses Keycloak to avoid complex setup in order to run the sample, Keycloak can easily be replaced with any OIDC compatible provider, including [Microsoft Entra Id](https://www.microsoft.com/security/business/identity-access/microsoft-entra-id).

## Overview

The sample has three components, all launched with a single `docker compose up`:

| Service | Port | Description |
|---------|------|-------------|
| **WebClient** | `http://localhost:8080` | Razor Pages web app with OIDC login and a chat UI that calls the AgentService |
| **AgentService** | `http://localhost:5001` | ASP.NET Minimal API hosting an expense approval agent with scope-authorized tools |
| **Keycloak** | `http://localhost:5002` | OIDC identity provider, auto-provisioned with realm, clients, scopes, and test users |

```
┌──────────────┐     OIDC login       ┌───────────┐
│  WebClient   │ ◄──────────────────► │ Keycloak  │
│  (Razor app) │     (browser flow)   │ (Docker)  │
│  :8080       │                      │ :5002     │
└──────┬───────┘                      └─────┬─────┘
       │ REST + Bearer token                │
       ▼                                    │
┌───────────────┐   JWT validation    ──────┘
│ AgentService  │ ◄──── (jwks from Keycloak)
│ (Minimal API) │
│ :5001         │
└───────────────┘
```

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and Docker Compose

## Configuring Environment Variables

The AgentService requires an OpenAI-compatible endpoint. Set these environment variables before running:

```bash
export OPENAI_API_KEY="<your-openai-api-key>"
export OPENAI_MODEL="gpt-4.1-mini"
```

## Running the Sample

### Option 1: Docker Compose (Recommended)

```bash
cd dotnet/samples/05-end-to-end/AspNetAgentAuthorization
docker compose up
```

This starts Keycloak, the AgentService, and the WebClient. Wait for Keycloak to finish importing the realm (you'll see `Running the server` in the logs).

#### Running in GitHub Codespaces

This sample has been built in such a way that it can be run from GitHub Codespaces.
The Agent Framework repository has a C# specific dev container, named "C# (.NET)", that is configured for Codespaces.

When running in Codespaces, the sample auto-detects the environment via
`CODESPACE_NAME` and `GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN` and configures
Keycloak and the web client accordingly. Just make the required ports public:

```bash
# Make Keycloak and WebClient ports publicly accessible
gh codespace ports visibility 5002:public 8080:public -c $CODESPACE_NAME

# Start the containers (Codespaces is auto-detected)
docker compose up
```

Then open the Codespaces-forwarded URL for port 8080 (shown in the **Ports** tab) in your browser.

### Option 2: Run Locally

1. Start Keycloak:
   ```bash
   docker compose up keycloak
   ```

2. In a new terminal, start the AgentService:
   ```bash
   cd Service
   dotnet run --urls "http://localhost:5001"
   ```

3. In another terminal, start the WebClient:
   ```bash
   cd RazorWebClient
   dotnet run --urls "http://localhost:8080"
   ```

## Using the Sample

1. Open `http://localhost:8080` in your browser
2. Click **Login** — you'll be redirected to Keycloak
3. Sign in with one of the pre-configured users:
   - **`testuser` / `password`** — can chat, view expenses, and approve expenses (up to €1,000)
   - **`viewer` / `password`** — can chat and view expenses, but **cannot approve** them
4. Try asking the agent:
   - _"Show me the pending expenses"_ — both users can do this
   - _"Approve expense #1"_ — only `testuser` can do this; `viewer` will be denied
   - _"Approve expense #3"_ — even `testuser` will be denied (€4,500 exceeds the €1,000 limit)

## Pre-Configured Keycloak Realm

The `keycloak/dev-realm.json` file auto-provisions:

| Resource | Details |
|----------|---------|
| **Realm** | `dev` |
| **Client: agent-service** | Confidential client (the API audience) |
| **Client: web-client** | Public client for the Razor app's OIDC login |
| **Scope: agent.chat** | Required to call the `/chat` endpoint |
| **Scope: expenses.view** | Required to list pending expenses |
| **Scope: expenses.approve** | Required to approve expenses |
| **User: testuser** | Has `agent.chat`, `expenses.view`, and `expenses.approve` scopes |
| **User: viewer** | Has `agent.chat` and `expenses.view` scopes (no approval) |

### Pre-Seeded Expenses

The service starts with five demo expenses:

| # | Description | Amount | Status |
|---|-------------|--------|--------|
| 1 | Conference travel — Berlin | €850 | Pending |
| 2 | Team dinner — Q4 celebration | €320 | Pending |
| 3 | Cloud infrastructure — annual renewal | €4,500 | Pending (over limit) |
| 4 | Office supplies — ergonomic keyboards | €675 | Pending |
| 5 | Client gift baskets — holiday season | €980 | Pending |

Keycloak admin console: `http://localhost:5002` (login: `admin` / `admin`).

## API Endpoints

### POST /chat (requires `agent.chat` scope)

```bash
# Get a token for testuser
TOKEN=$(curl -s -X POST http://localhost:5002/realms/dev/protocol/openid-connect/token \
  -d "grant_type=password&client_id=web-client&username=testuser&password=password&scope=openid agent.chat expenses.view expenses.approve" \
  | jq -r '.access_token')

# Chat with the agent
curl -X POST http://localhost:5001/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "Show me the pending expenses"}'
```

## Key Concepts Demonstrated

- **Endpoint-Level Authorization** — The `/chat` endpoint requires the `agent.chat` scope, gating access to the agent itself
- **Tool-Level Authorization** — Each agent tool checks its own scope (`expenses.view`, `expenses.approve`) at runtime, so different users have different capabilities within the same chat session
- **Scope-Based Role Mapping** — Keycloak realm roles map to OAuth scopes, allowing administrators to control which users can access which agent capabilities
