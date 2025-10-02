# Agent Middleware 

This sample demonstrates how to add middleware to intercept:
- Chat client calls (global and per‑request)
- Agent runs (guardrails and PII filtering)
- Function calling (logging/override)

## What This Sample Shows

1. Azure OpenAI integration via `AzureOpenAIClient` and `AzureCliCredential`
2. Chat client middleware using `ChatClientBuilder.Use(...)`
3. Agent run middleware (PII redaction and wording guardrails)
4. Function invocation middleware (logging and overriding a tool result)
5. Per‑request chat client middleware
6. Per‑request function pipeline with approval
7. Combining agent‑level and per‑request middleware

## Function Invocation Middleware

Not all agents support function invocation middleware.

Attempting to use function middleware on agents that do not wrap a ChatClientAgent or derives from it will throw an InvalidOperationException.

## Prerequisites

1. Environment variables:
   - `AZURE_OPENAI_ENDPOINT`: Your Azure OpenAI endpoint
   - `AZURE_OPENAI_DEPLOYMENT_NAME`: Chat deployment name (optional; defaults to `gpt-4o`)
2. Sign in with Azure CLI (PowerShell):
   ```powershell
   az login
   ```

## Running the Sample

Use PowerShell:
```powershell
cd dotnet/samples/GettingStarted/Agents/Agent_Step14_Middleware
dotnet run
```

