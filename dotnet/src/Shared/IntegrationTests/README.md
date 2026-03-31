# Integration Tests

Common Integration test files.

To use this in your project, add the following to your `.csproj` file:

```xml
<PropertyGroup>
  <InjectSharedIntegrationTestCode>true</InjectSharedIntegrationTestCode>
</PropertyGroup>
```

## Configuration

Integration tests use flat environment variable names for configuration.
Use `TestConfiguration.GetValue(key)` or `TestConfiguration.GetRequiredValue(key)` to access values.

Available keys are defined as constants in `TestSettings.cs`:

| Key | Description |
|---|---|
| `ANTHROPIC_API_KEY` | API key for Anthropic |
| `ANTHROPIC_CHAT_MODEL_NAME` | Anthropic chat model name |
| `ANTHROPIC_REASONING_MODEL_NAME` | Anthropic reasoning model name |
| `ANTHROPIC_SERVICE_ID` | Anthropic service ID |
| `AZURE_AI_BING_CONNECTION_ID` | Azure AI Bing connection ID |
| `AZURE_AI_MEMORY_STORE_ID` | Azure AI Memory store name |
| `AZURE_AI_MODEL_DEPLOYMENT_NAME` | Azure AI model deployment name |
| `AZURE_AI_PROJECT_ENDPOINT` | Azure AI project endpoint |
| `COPILOTSTUDIO_AGENT_APP_ID` | Copilot Studio agent app ID |
| `COPILOTSTUDIO_DIRECT_CONNECT_URL` | Copilot Studio direct connect URL |
| `COPILOTSTUDIO_TENANT_ID` | Copilot Studio tenant ID |
| `MEM0_API_KEY` | API key for Mem0 |
| `MEM0_ENDPOINT` | Mem0 service endpoint |
| `OPENAI_API_KEY` | API key for OpenAI |
| `OPENAI_CHAT_MODEL_NAME` | OpenAI chat model name |
| `OPENAI_REASONING_MODEL_NAME` | OpenAI reasoning model name |
| `OPENAI_SERVICE_ID` | OpenAI service ID |
