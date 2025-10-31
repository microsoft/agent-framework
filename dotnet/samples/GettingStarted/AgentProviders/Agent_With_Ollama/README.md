# Prerequisites

Before you begin, ensure you have the following prerequisites:

- .NET 8.0 SDK or later
- Docker installed and running on your machine
- An Ollama model downloaded into Ollama

To download and start Ollama on Docker using CPU, run the following command in your terminal.

```powershell
docker run -d -v "c:\temp\ollama:/root/.ollama" -p 11434:11434 --name ollama ollama/ollama
```

To download and start Ollama on Docker using GPU, run the following command in your terminal.

```powershell
docker run -d --gpus=all -v "c:\temp\ollama:/root/.ollama" -p 11434:11434 --name ollama ollama/ollama
```

After the container has started, launch a Terminal window for the docker container, e.g. if using docker desktop, choose Open in Terminal from actions.

From this terminal download the required models, e.g. here we are downloading the phi3 model.

```text
ollama pull gpt-oss
```

Set the following environment variables:

```powershell
$env:OLLAMA_ENDPOINT="http://localhost:11434"
$env:OLLAMA_MODEL_NAME="gpt-oss"
```

## Known Limitations

### Structured Output

Ollama models (including gpt-oss, llama3, phi3, etc.) do not support native JSON schema-based structured output. If you try to use `RunAsync<T>()` for structured output with the default settings, you may receive empty responses.

To use structured output with Ollama models, you must set `useJsonSchemaResponseFormat: false`:

```csharp
// This will NOT work with Ollama (may return empty responses)
var response = await agent.RunAsync<MyType>("prompt");

// This WILL work with Ollama
var response = await agent.RunAsync<MyType>("prompt", useJsonSchemaResponseFormat: false);
```

Additionally, you should include instructions in your agent prompt to guide the output format:

```csharp
AIAgent agent = new OllamaApiClient(new Uri(endpoint), modelName)
    .CreateAIAgent(
        instructions: "You are a helpful assistant. Always respond with valid JSON matching the requested format.",
        name: "Assistant");
```

For more details on structured output and model compatibility, see the [Structured Output sample](../../Agents/Agent_Step05_StructuredOutput/README.md).
