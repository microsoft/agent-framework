# Creating an AIAgent with Salesforce Agentforce

This sample demonstrates how to create an AIAgent that connects to a **Salesforce Agentforce** (Einstein AI Agent) through the Agentforce REST API.

The agent authenticates via the OAuth 2.0 client-credentials flow, creates a conversational session, and forwards messages to a deployed Agentforce agent in your Salesforce org.

## Prerequisites

Before you begin, ensure you have the following:

- .NET 8.0 SDK or later
- A Salesforce org with an **Agentforce agent** deployed and activated
- A **Connected App** (External Client App) configured for the OAuth 2.0 client-credentials flow

### Salesforce Setup

1. **Create an Agentforce agent** in your Salesforce org via Setup → Agents. Note the **Agent ID**.
2. **Create a Connected App** (or External Client App) with:
   - OAuth 2.0 enabled
   - Grant type: `client_credentials`
   - Scopes: `api`, `cdp_query_api` (or as required by your agent)
3. Copy the **Consumer Key** and **Consumer Secret**.
4. Make sure your Salesforce My Domain is active. The domain host looks like `your-org.my.salesforce.com`.

### Environment Variables

Set the following environment variables before running the sample:

**PowerShell**

```powershell
$env:AGENTFORCE_DOMAIN="your-org.my.salesforce.com"           # Salesforce My Domain host
$env:AGENTFORCE_CONSUMER_KEY="your-connected-app-consumer-key" # OAuth consumer key
$env:AGENTFORCE_CONSUMER_SECRET="your-consumer-secret"         # OAuth consumer secret
$env:AGENTFORCE_AGENT_ID="your-agent-id"                       # Agentforce Agent ID
```

**Bash / macOS / Linux**

```bash
export AGENTFORCE_DOMAIN="your-org.my.salesforce.com"
export AGENTFORCE_CONSUMER_KEY="your-connected-app-consumer-key"
export AGENTFORCE_CONSUMER_SECRET="your-consumer-secret"
export AGENTFORCE_AGENT_ID="your-agent-id"
```

## Running the Sample

```bash
dotnet run
```

The sample will:

1. Authenticate with Salesforce using the client-credentials OAuth flow.
2. Create an Agentforce conversational session.
3. Send a message to the agent and print the full response (**non-streaming**).
4. Send a second message and print each update as it arrives (**streaming**).

## How It Works

```
┌─────────────┐       ┌──────────────────┐       ┌──────────────────────────┐
│  Your App   │──────▶│  AgentforceAgent  │──────▶│  Salesforce Agentforce   │
│ (Program.cs)│◀──────│  (AIAgent)        │◀──────│  REST API                │
└─────────────┘       └──────────────────┘       └──────────────────────────┘
```

- **`AgentforceConfig`** — Holds credentials and the agent identity.
- **`AgentforceAgent`** — Implements `AIAgent` and manages sessions & message round-trips.
- **`AgentforceClient`** — Low-level HTTP client that calls the Agentforce REST API (OAuth token, session CRUD, send message).

Because `AgentforceAgent` extends `AIAgent`, it can be used anywhere the framework expects an agent — including multi-agent orchestration and workflow scenarios.
