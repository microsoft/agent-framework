# InMemory special casing sample

This sample demonstrates how to work with the in-memory chat message store and thread serialization separately while persisting and restoring them.

It shows how to:

- Attempt to load a previously serialized agent thread and chat history in parallel
- Create a new thread and empty chat history if none exist
- Merge loaded chat history into the thread's in-memory store
- Run the agent with the reconstructed state
- Extract, clear, and persist the updated chat history and thread for later continuation

## Prerequisites

- .NET 8.0 SDK or later
- Azure OpenAI endpoint and deployment
- Authenticated Azure CLI (`az login`) with `Cognitive Services OpenAI Contributor` role

Environment variables used:

- `AZURE_OPENAI_ENDPOINT` – The Azure OpenAI endpoint
- `AZURE_OPENAI_DEPLOYMENT_NAME` – The deployment name (e.g. `gpt-4o-mini`)

## Running the sample

```bash
cd dotnet/samples/GettingStarted/Agents/InMemorySpecialCasing
dotnet run
```

You can run it multiple times to see the persisted state being reused.
