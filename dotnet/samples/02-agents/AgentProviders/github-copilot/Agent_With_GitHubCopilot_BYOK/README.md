# Prerequisites

Before you begin, ensure you have the following prerequisites:

- .NET 10 SDK or later
- GitHub Copilot CLI installed and available in your PATH (or provide a custom path)
- An OpenAI-compatible endpoint and API key (OpenAI, Azure OpenAI, or a compatible service such as vLLM, LiteLLM, or Ollama)

## Setting up GitHub Copilot CLI

To use this sample, you need to have the GitHub Copilot CLI installed. You can install it by
following the instructions at:
https://github.com/github/copilot-sdk

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `BYOK_BASE_URL` | Base URL of your OpenAI-compatible endpoint | *(required)* |
| `BYOK_API_KEY` | API key for that endpoint | *(required)* |
| `BYOK_MODEL_ID` | Model name to request (e.g. "gpt-4o") | `gpt-4o` |

## Running the Sample

```powershell
dotnet run
```

The sample will:

1. Create a GitHub Copilot client with default options
2. Configure a session with a `Provider` (BYOK) pointing at your own endpoint instead of the
   default GitHub Copilot backend
3. Send a message to the agent
4. Stream the response

## About BYOK (Bring Your Own Key)

BYOK lets you route model requests through your own API keys and infrastructure instead of the
GitHub Copilot backend — useful for enterprise deployments, custom hosting, or direct billing
arrangements. See [GitHub's BYOK documentation](https://docs.github.com/en/copilot/how-tos/copilot-sdk/auth/byok)
for the full list of supported providers and configuration options.

```csharp
using GitHub.Copilot;
using Microsoft.Agents.AI;

await using CopilotClient copilotClient = new();
await copilotClient.StartAsync();

SessionConfig sessionConfig = new()
{
    // BYOK requires Model to also be set at the session level.
    Model = "gpt-4o",
    Provider = new ProviderConfig
    {
        Type = "openai",
        WireApi = "completions",
        BaseUrl = "https://api.example.com/v1",
        ApiKey = "your-api-key",
        ModelId = "gpt-4o",
    },
};

AIAgent agent = copilotClient.AsAIAgent(sessionConfig, ownsClient: true);
AgentResponse response = await agent.RunAsync("Hello!");
Console.WriteLine(response);
```

> **Note:** BYOK uses static credentials only — dynamic token refresh is not automatic, and
> model availability depends entirely on your provider's offerings. Usage is tracked through
> your provider rather than GitHub.
