# Custom session storage provider

This sample shows how to provide custom session storage to `ResponsesHostServer`.
The `CustomSessionStoreProvider` selects storage based on the resolved hosting
configuration:

- Local runs use the in-memory `SessionStore` and do not require Cosmos DB.
- Foundry-hosted runs use the custom `CosmosSessionStore` implementation.

The sample customizes agent-session persistence only. The host's default providers
continue to manage workflow checkpoints and function approvals.

## Azure Cosmos DB setup

Before deploying the sample, create an Azure Cosmos DB database and container. The
container must use `/user_id` as its partition key. Each session document includes
the Foundry platform user ID, so session IDs and data are isolated between users.
Set these environment variables to
the existing resources:

- `COSMOS_CONNECTION_STRING`
- `COSMOS_DATABASE_NAME`
- `COSMOS_CONTAINER_NAME`

See [main.py](main.py) for the complete provider and store implementations.

## Running locally

Copy `.env.example` to `.env`, set the Foundry project and model values, and leave
the Cosmos values unset. The provider creates one in-memory store for the lifetime
of the local server process.

Follow [Running the Agent Host Locally](../../README.md#running-the-agent-host-locally)
in the parent README, then send a request:

```bash
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" -d '{"input": "Hi"}'
```

Local session data is lost when the process exits.

## Deploying to Foundry

Set all variables in `.env.example`, including the Cosmos settings, and follow
[Deploying the Agent to Foundry](../../README.md#deploying-the-agent-to-foundry)
in the parent README. The hosted provider initializes Cosmos DB lazily on its first
request and reuses the client and container for later requests. Each request receives
a session store scoped to the non-empty user ID supplied by Foundry.
