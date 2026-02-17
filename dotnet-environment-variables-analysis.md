# .NET Samples and Integration Tests - Environment Variables and User Secrets

This document provides a comprehensive analysis of environment variables and user secrets usage across .NET samples and integration tests in the agent-framework repository.

## Environment Variables and Configuration Keys

| Variable/Secret Name | Inferred Meaning/Usage | Referencing Projects (relative to repo root) |
|---------------------|------------------------|---------------------------------------------|
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI service endpoint URL | `dotnet/samples/Purview/AgentWithPurview`<br>`dotnet/samples/HostedAgents/AgentsInWorkflows`<br>`dotnet/samples/HostedAgents/AgentWithHostedMCP`<br>`dotnet/samples/HostedAgents/AgentWithTextSearchRag`<br>`dotnet/samples/GettingStarted/AgentProviders/Agent_With_AzureOpenAIChatCompletion`<br>`dotnet/samples/GettingStarted/AgentProviders/Agent_With_AzureOpenAIResponses`<br>`dotnet/samples/GettingStarted/AgentWithMemory/AgentWithMemory_Step01_ChatHistoryMemory`<br>`dotnet/samples/GettingStarted/AgentWithMemory/AgentWithMemory_Step02_MemoryUsingMem0`<br>`dotnet/samples/GettingStarted/AgentWithMemory/AgentWithMemory_Step03_CustomMemory`<br>`dotnet/samples/GettingStarted/Agents/Agent_Step01_Running`<br>`dotnet/samples/GettingStarted/Agents/Agent_Step02_MultiturnConversation`<br>`dotnet/samples/GettingStarted/Agents/Agent_Step03_UsingFunctionTools`<br>`dotnet/samples/GettingStarted/Agents/Agent_Step04_UsingFunctionToolsWithApprovals`<br>`dotnet/samples/GettingStarted/Agents/Agent_Step05_StructuredOutput`<br>`dotnet/samples/GettingStarted/Agents/Agent_Step06_PersistedConversations`<br>`dotnet/samples/GettingStarted/Agents/Agent_Step07_3rdPartyChatHistoryStorage`<br>`dotnet/samples/GettingStarted/Agents/Agent_Step08_Observability`<br>`dotnet/samples/GettingStarted/Agents/Agent_Step09_DependencyInjection`<br>`dotnet/samples/GettingStarted/Agents/Agent_Step11_UsingImages`<br>`dotnet/samples/GettingStarted/Agents/Agent_Step12_AsFunctionTool`<br>`dotnet/samples/GettingStarted/Agents/Agent_Step14_Middleware`<br>`dotnet/samples/GettingStarted/Agents/Agent_Step15_Plugins`<br>`dotnet/samples/GettingStarted/Agents/Agent_Step16_ChatReduction`<br>`dotnet/samples/GettingStarted/Agents/Agent_Step17_BackgroundResponses`<br>`dotnet/samples/GettingStarted/Agents/Agent_Step19_Declarative`<br>`dotnet/samples/GettingStarted/Agents/Agent_Step20_AdditionalAIContext`<br>`dotnet/samples/GettingStarted/AgentWithRAG/AgentWithRAG_Step01_BasicTextRAG`<br>`dotnet/samples/GettingStarted/AgentWithRAG/AgentWithRAG_Step02_CustomVectorStoreRAG`<br>`dotnet/samples/GettingStarted/AgentWithRAG/AgentWithRAG_Step03_CustomRAGDataSource`<br>`dotnet/samples/GettingStarted/ModelContextProtocol/Agent_MCP_Server`<br>`dotnet/samples/GettingStarted/ModelContextProtocol/Agent_MCP_Server_Auth`<br>`dotnet/samples/GettingStarted/ModelContextProtocol/ResponseAgent_Hosted_MCP`<br>`dotnet/samples/GettingStarted/DeclarativeAgents/ChatClient`<br>`dotnet/samples/GettingStarted/AgentOpenTelemetry`<br>`dotnet/samples/GettingStarted/A2A/A2AAgent_AsFunctionTools`<br>`dotnet/samples/GettingStarted/Workflows/_Foundational/03_AgentsInWorkflows`<br>`dotnet/samples/GettingStarted/Workflows/_Foundational/04_AgentWorkflowPatterns`<br>`dotnet/samples/GettingStarted/Workflows/_Foundational/07_MixedWorkflowAgentsAndExecutors`<br>`dotnet/samples/GettingStarted/Workflows/_Foundational/08_WriterCriticWorkflow`<br>`dotnet/samples/GettingStarted/Workflows/Agents/CustomAgentExecutors`<br>`dotnet/samples/GettingStarted/Workflows/Agents/GroupChatToolApproval`<br>`dotnet/samples/GettingStarted/Workflows/Agents/WorkflowAsAnAgent`<br>`dotnet/samples/GettingStarted/Workflows/ConditionalEdges/01_EdgeCondition`<br>`dotnet/samples/GettingStarted/Workflows/ConditionalEdges/02_SwitchCase`<br>`dotnet/samples/GettingStarted/Workflows/ConditionalEdges/03_MultiSelection`<br>`dotnet/samples/GettingStarted/Workflows/Concurrent/Concurrent`<br>`dotnet/samples/GettingStarted/Workflows/Observability/WorkflowAsAnAgent`<br>`dotnet/samples/Durable/Agents/ConsoleApps/01_SingleAgent`<br>`dotnet/samples/Durable/Agents/ConsoleApps/02_AgentOrchestration_Chaining`<br>`dotnet/samples/Durable/Agents/ConsoleApps/03_AgentOrchestration_Concurrency`<br>`dotnet/samples/Durable/Agents/ConsoleApps/04_AgentOrchestration_Conditionals`<br>`dotnet/samples/Durable/Agents/ConsoleApps/05_AgentOrchestration_HITL`<br>`dotnet/samples/Durable/Agents/ConsoleApps/06_LongRunningTools`<br>`dotnet/samples/Durable/Agents/ConsoleApps/07_ReliableStreaming`<br>`dotnet/samples/Durable/Agents/AzureFunctions/01_SingleAgent`<br>`dotnet/samples/Durable/Agents/AzureFunctions/02_AgentOrchestration_Chaining`<br>`dotnet/samples/Durable/Agents/AzureFunctions/03_AgentOrchestration_Concurrency`<br>`dotnet/samples/Durable/Agents/AzureFunctions/04_AgentOrchestration_Conditionals`<br>`dotnet/samples/Durable/Agents/AzureFunctions/05_AgentOrchestration_HITL`<br>`dotnet/samples/Durable/Agents/AzureFunctions/06_LongRunningTools`<br>`dotnet/samples/Durable/Agents/AzureFunctions/07_AgentAsMcpTool`<br>`dotnet/samples/Durable/Agents/AzureFunctions/08_ReliableStreaming`<br>`dotnet/samples/AGUIClientServer/AGUIServer`<br>`dotnet/samples/AGUIWebChat/Server`<br>`dotnet/samples/GettingStarted/AGUI/Step01_GettingStarted/Server`<br>`dotnet/samples/GettingStarted/AGUI/Step02_BackendTools/Server`<br>`dotnet/samples/GettingStarted/AGUI/Step03_FrontendTools/Server`<br>`dotnet/samples/GettingStarted/AGUI/Step04_HumanInLoop/Server`<br>`dotnet/samples/GettingStarted/AGUI/Step05_StateManagement/Server`<br>`dotnet/samples/GettingStarted/DevUI/DevUI_Step01_BasicUsage` |
| `AZURE_OPENAI_DEPLOYMENT_NAME` | Azure OpenAI model deployment name | Same projects as `AZURE_OPENAI_ENDPOINT` above |
| `AZURE_OPENAI_KEY` | Azure OpenAI API key (optional for key-based authentication) | `dotnet/samples/Durable/Agents/ConsoleApps/01_SingleAgent`<br>`dotnet/samples/Durable/Agents/ConsoleApps/02_AgentOrchestration_Chaining`<br>`dotnet/samples/Durable/Agents/ConsoleApps/03_AgentOrchestration_Concurrency`<br>`dotnet/samples/Durable/Agents/ConsoleApps/04_AgentOrchestration_Conditionals`<br>`dotnet/samples/Durable/Agents/ConsoleApps/05_AgentOrchestration_HITL`<br>`dotnet/samples/Durable/Agents/ConsoleApps/06_LongRunningTools`<br>`dotnet/samples/Durable/Agents/ConsoleApps/07_ReliableStreaming`<br>`dotnet/samples/Durable/Agents/AzureFunctions/01_SingleAgent`<br>`dotnet/samples/Durable/Agents/AzureFunctions/02_AgentOrchestration_Chaining`<br>`dotnet/samples/Durable/Agents/AzureFunctions/03_AgentOrchestration_Concurrency`<br>`dotnet/samples/Durable/Agents/AzureFunctions/04_AgentOrchestration_Conditionals`<br>`dotnet/samples/Durable/Agents/AzureFunctions/05_AgentOrchestration_HITL`<br>`dotnet/samples/Durable/Agents/AzureFunctions/06_LongRunningTools`<br>`dotnet/samples/Durable/Agents/AzureFunctions/07_AgentAsMcpTool`<br>`dotnet/samples/Durable/Agents/AzureFunctions/08_ReliableStreaming` |
| `AZURE_OPENAI_DEPLOYMENT` | Alternative name for Azure OpenAI deployment (used in Durable samples) | All projects under `dotnet/samples/Durable/Agents/ConsoleApps/`<br>All projects under `dotnet/samples/Durable/Agents/AzureFunctions/` |
| `AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME` | Azure OpenAI embedding model deployment name | `dotnet/samples/GettingStarted/AgentWithMemory/AgentWithMemory_Step01_ChatHistoryMemory`<br>`dotnet/samples/GettingStarted/AgentWithRAG/AgentWithRAG_Step01_BasicTextRAG`<br>`dotnet/samples/GettingStarted/AgentWithRAG/AgentWithRAG_Step02_CustomVectorStoreRAG` |
| `AZURE_FOUNDRY_PROJECT_ENDPOINT` | Azure AI Foundry project endpoint URL | `dotnet/samples/GettingStarted/AgentProviders/Agent_With_AzureAIAgentsPersistent`<br>`dotnet/samples/GettingStarted/AgentProviders/Agent_With_AzureAIProject`<br>`dotnet/samples/GettingStarted/AgentWithRAG/AgentWithRAG_Step04_FoundryServiceRAG`<br>`dotnet/samples/GettingStarted/Agents/Agent_Step10_AsMcpTool`<br>`dotnet/samples/GettingStarted/Agents/Agent_Step18_DeepResearch`<br>`dotnet/samples/GettingStarted/FoundryAgents/FoundryAgents_Step01.1_Basics`<br>`dotnet/samples/GettingStarted/FoundryAgents/FoundryAgents_Step01.2_Running`<br>`dotnet/samples/GettingStarted/FoundryAgents/FoundryAgents_Step02_MultiturnConversation`<br>`dotnet/samples/GettingStarted/FoundryAgents/FoundryAgents_Step03_UsingFunctionTools`<br>`dotnet/samples/GettingStarted/FoundryAgents/FoundryAgents_Step04_UsingFunctionToolsWithApprovals`<br>`dotnet/samples/GettingStarted/FoundryAgents/FoundryAgents_Step05_StructuredOutput`<br>`dotnet/samples/GettingStarted/FoundryAgents/FoundryAgents_Step06_PersistedConversations`<br>`dotnet/samples/GettingStarted/FoundryAgents/FoundryAgents_Step07_Observability`<br>`dotnet/samples/GettingStarted/FoundryAgents/FoundryAgents_Step08_DependencyInjection`<br>`dotnet/samples/GettingStarted/FoundryAgents/FoundryAgents_Step09_UsingMcpClientAsTools`<br>`dotnet/samples/GettingStarted/FoundryAgents/FoundryAgents_Step10_UsingImages`<br>`dotnet/samples/GettingStarted/FoundryAgents/FoundryAgents_Step11_AsFunctionTool`<br>`dotnet/samples/GettingStarted/FoundryAgents/FoundryAgents_Step12_Middleware`<br>`dotnet/samples/GettingStarted/FoundryAgents/FoundryAgents_Step13_Plugins`<br>`dotnet/samples/GettingStarted/FoundryAgents/FoundryAgents_Step14_CodeInterpreter`<br>`dotnet/samples/GettingStarted/FoundryAgents/FoundryAgents_Step15_ComputerUse`<br>`dotnet/samples/GettingStarted/FoundryAgents/FoundryAgents_Step27_LocalMCP`<br>`dotnet/samples/GettingStarted/ModelContextProtocol/FoundryAgent_Hosted_MCP`<br>`dotnet/samples/GettingStarted/Workflows/Agents/FoundryAgent` |
| `AZURE_FOUNDRY_PROJECT_DEPLOYMENT_NAME` | Azure AI Foundry model deployment name | Same projects as `AZURE_FOUNDRY_PROJECT_ENDPOINT` above |
| `AZURE_FOUNDRY_PROJECT_DEEP_RESEARCH_DEPLOYMENT_NAME` | Azure AI Foundry deep research model deployment name | `dotnet/samples/GettingStarted/Agents/Agent_Step18_DeepResearch` |
| `AZURE_FOUNDRY_OPENAI_ENDPOINT` | Azure AI Foundry OpenAI-compatible endpoint | `dotnet/samples/GettingStarted/AgentProviders/Agent_With_AzureFoundryModel` |
| `AZURE_FOUNDRY_OPENAI_API_KEY` | Azure AI Foundry OpenAI-compatible API key | `dotnet/samples/GettingStarted/AgentProviders/Agent_With_AzureFoundryModel` |
| `AZURE_FOUNDRY_MODEL_DEPLOYMENT` | Azure AI Foundry model deployment name | `dotnet/samples/GettingStarted/AgentProviders/Agent_With_AzureFoundryModel` |
| `OPENAI_API_KEY` | OpenAI API key for direct OpenAI service access | `dotnet/samples/GettingStarted/AgentProviders/Agent_With_OpenAIChatCompletion`<br>`dotnet/samples/GettingStarted/AgentProviders/Agent_With_OpenAIResponses`<br>`dotnet/samples/GettingStarted/AgentProviders/Agent_With_OpenAIAssistants`<br>`dotnet/samples/GettingStarted/AgentWithOpenAI/Agent_OpenAI_Step01_Running`<br>`dotnet/samples/GettingStarted/AgentWithOpenAI/Agent_OpenAI_Step02_Reasoning`<br>`dotnet/samples/GettingStarted/AgentWithOpenAI/Agent_OpenAI_Step03_CreateFromChatClient`<br>`dotnet/samples/GettingStarted/AgentWithOpenAI/Agent_OpenAI_Step04_CreateFromOpenAIResponseClient`<br>`dotnet/samples/GettingStarted/AgentWithOpenAI/Agent_OpenAI_Step05_Conversation`<br>`dotnet/samples/GettingStarted/Workflows/_Foundational/05_MultiModelService` |
| `OPENAI_MODEL` | OpenAI model identifier (e.g., gpt-4o-mini) | Same projects as `OPENAI_API_KEY` above |
| `ANTHROPIC_API_KEY` | Anthropic API key for Claude models | `dotnet/samples/GettingStarted/AgentProviders/Agent_With_Anthropic`<br>`dotnet/samples/GettingStarted/AgentWithAnthropic/Agent_Anthropic_Step01_Running`<br>`dotnet/samples/GettingStarted/AgentWithAnthropic/Agent_Anthropic_Step02_Reasoning`<br>`dotnet/samples/GettingStarted/AgentWithAnthropic/Agent_Anthropic_Step03_UsingFunctionTools`<br>`dotnet/samples/GettingStarted/AgentWithAnthropic/Agent_Anthropic_Step04_UsingSkills`<br>`dotnet/tests/AnthropicChatCompletion.IntegrationTests` (via configuration) |
| `ANTHROPIC_MODEL` | Anthropic model identifier (e.g., claude-haiku-4-5) | `dotnet/samples/GettingStarted/AgentWithAnthropic/Agent_Anthropic_Step01_Running`<br>`dotnet/samples/GettingStarted/AgentWithAnthropic/Agent_Anthropic_Step02_Reasoning`<br>`dotnet/samples/GettingStarted/AgentWithAnthropic/Agent_Anthropic_Step03_UsingFunctionTools`<br>`dotnet/samples/GettingStarted/AgentWithAnthropic/Agent_Anthropic_Step04_UsingSkills` |
| `ANTHROPIC_DEPLOYMENT_NAME` | Anthropic deployment name | `dotnet/samples/GettingStarted/AgentProviders/Agent_With_Anthropic` |
| `ANTHROPIC_RESOURCE` | Anthropic resource identifier (optional) | `dotnet/samples/GettingStarted/AgentProviders/Agent_With_Anthropic` |
| `ANTHROPIC_APIKEY` | Alternative Anthropic API key name | `dotnet/samples/GettingStarted/Workflows/_Foundational/05_MultiModelService` |
| `GOOGLE_GENAI_API_KEY` | Google Generative AI (Gemini) API key | `dotnet/samples/GettingStarted/AgentProviders/Agent_With_GoogleGemini` |
| `GOOGLE_GENAI_MODEL` | Google Generative AI model identifier | `dotnet/samples/GettingStarted/AgentProviders/Agent_With_GoogleGemini` |
| `OLLAMA_ENDPOINT` | Ollama local model server endpoint | `dotnet/samples/GettingStarted/AgentProviders/Agent_With_Ollama` |
| `OLLAMA_MODEL_NAME` | Ollama model name | `dotnet/samples/GettingStarted/AgentProviders/Agent_With_Ollama` |
| `ONNX_MODEL_PATH` | Path to ONNX model file | `dotnet/samples/GettingStarted/AgentProviders/Agent_With_ONNX` |
| `BEDROCK_ACCESSKEY` | AWS Bedrock access key | `dotnet/samples/GettingStarted/Workflows/_Foundational/05_MultiModelService` |
| `BEDROCK_SECRETACCESSKEY` | AWS Bedrock secret access key | `dotnet/samples/GettingStarted/Workflows/_Foundational/05_MultiModelService` |
| `MEM0_ENDPOINT` | Mem0 memory service endpoint | `dotnet/samples/GettingStarted/AgentWithMemory/AgentWithMemory_Step02_MemoryUsingMem0`<br>`dotnet/tests/Microsoft.Agents.AI.Mem0.IntegrationTests` (via configuration) |
| `MEM0_APIKEY` | Mem0 API key | `dotnet/samples/GettingStarted/AgentWithMemory/AgentWithMemory_Step02_MemoryUsingMem0`<br>`dotnet/tests/Microsoft.Agents.AI.Mem0.IntegrationTests` (via configuration) |
| `PURVIEW_CLIENT_APP_ID` | Microsoft Purview client application ID | `dotnet/samples/Purview/AgentWithPurview` |
| `A2A_AGENT_HOST` | Agent-to-Agent communication host URL | `dotnet/samples/GettingStarted/AgentProviders/Agent_With_A2A`<br>`dotnet/samples/GettingStarted/A2A/A2AAgent_PollingForTaskCompletion`<br>`dotnet/samples/GettingStarted/A2A/A2AAgent_AsFunctionTools` |
| `BING_CONNECTION_ID` | Bing connection identifier for search | `dotnet/samples/GettingStarted/Agents/Agent_Step18_DeepResearch` |
| `DURABLE_TASK_SCHEDULER_CONNECTION_STRING` | Connection string for Durable Task Scheduler backend | All projects under `dotnet/samples/Durable/Agents/ConsoleApps/`<br>`dotnet/tests/Microsoft.Agents.AI.DurableTask.IntegrationTests` (via configuration)<br>`dotnet/tests/Microsoft.Agents.AI.Hosting.AzureFunctions.IntegrationTests` (via configuration) |
| `REDIS_CONNECTION_STRING` | Redis connection string for streaming | `dotnet/samples/Durable/Agents/ConsoleApps/07_ReliableStreaming`<br>`dotnet/samples/Durable/Agents/AzureFunctions/08_ReliableStreaming` |
| `REDIS_STREAM_TTL_MINUTES` | Redis stream time-to-live in minutes | `dotnet/samples/Durable/Agents/ConsoleApps/07_ReliableStreaming`<br>`dotnet/samples/Durable/Agents/AzureFunctions/08_ReliableStreaming` |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | Azure Application Insights connection string | `dotnet/samples/GettingStarted/Agents/Agent_Step08_Observability`<br>`dotnet/samples/GettingStarted/FoundryAgents/FoundryAgents_Step07_Observability`<br>`dotnet/samples/GettingStarted/AgentOpenTelemetry`<br>`dotnet/samples/GettingStarted/Workflows/Observability/ApplicationInsights`<br>`dotnet/samples/GettingStarted/Workflows/Observability/WorkflowAsAnAgent`<br>`dotnet/samples/AgentWebChat/AgentWebChat.ServiceDefaults` (commented out) |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OpenTelemetry OTLP exporter endpoint | `dotnet/samples/GettingStarted/AgentOpenTelemetry`<br>`dotnet/samples/AgentWebChat/AgentWebChat.ServiceDefaults` |
| `OTLP_ENDPOINT` | Alternative OpenTelemetry endpoint name | `dotnet/samples/GettingStarted/Workflows/Observability/AspireDashboard`<br>`dotnet/samples/GettingStarted/Workflows/Observability/WorkflowAsAnAgent` |
| `SERVER_URL` | AGUI/web client server URL | `dotnet/samples/AGUIWebChat/Client` |
| `AGUI_SERVER_URL` | AGUI server URL for client connections | `dotnet/samples/GettingStarted/AGUI/Step01_GettingStarted/Client`<br>`dotnet/samples/GettingStarted/AGUI/Step02_BackendTools/Client`<br>`dotnet/samples/GettingStarted/AGUI/Step03_FrontendTools/Client`<br>`dotnet/samples/GettingStarted/AGUI/Step04_HumanInLoop/Client`<br>`dotnet/samples/GettingStarted/AGUI/Step05_StateManagement/Client` |
| `AzureWebJobsStorage` | Azure Functions storage account connection | All projects under `dotnet/samples/Durable/Agents/AzureFunctions/`<br>`dotnet/tests/Microsoft.Agents.AI.Hosting.AzureFunctions.IntegrationTests` |
| `COSMOS_PRESERVE_CONTAINERS` | Flag to preserve Cosmos DB containers in tests | `dotnet/tests/Microsoft.Agents.AI.CosmosNoSql.UnitTests` |
| `COSMOS_EMULATOR_AVAILABLE` | Flag indicating Cosmos DB emulator availability | `dotnet/tests/Microsoft.Agents.AI.CosmosNoSql.UnitTests` |
| `AF_SHOW_ALL_DEMO_SETTING_VALUES` | Flag to show all demo setting values (debugging) | `dotnet/src/Shared/Demos/SampleEnvironment.cs` |
| `FOUNDRY_PROJECT_ENDPOINT` | Foundry project endpoint (Declarative Workflows) | `dotnet/tests/Microsoft.Agents.AI.Workflows.Declarative.IntegrationTests` (via configuration) |
| `FOUNDRY_MODEL_DEPLOYMENT_NAME` | Foundry model deployment name (Declarative Workflows) | `dotnet/tests/Microsoft.Agents.AI.Workflows.Declarative.IntegrationTests` (via configuration) |
| `FOUNDRY_MEDIA_DEPLOYMENT_NAME` | Foundry media deployment name (Declarative Workflows) | `dotnet/tests/Microsoft.Agents.AI.Workflows.Declarative.IntegrationTests` (via configuration) |
| `FOUNDRY_CONNECTION_GROUNDING_TOOL` | Foundry grounding tool connection (Declarative Workflows) | `dotnet/tests/Microsoft.Agents.AI.Workflows.Declarative.IntegrationTests` (via configuration) |

## User Secrets IDs

The following User Secrets IDs are configured in various projects:

| User Secret ID | Projects |
|----------------|----------|
| `b842df34-390f-490d-9dc0-73909363ad16` | M365Agent sample |
| `a8b2e9f0-1ea3-4f18-9d41-42d1a6f8fe10` | `dotnet/samples/AGUIClientServer/AGUIClient`<br>`dotnet/samples/AGUIClientServer/AGUIServer` |
| `b9c3f1e1-2fb4-5g29-0e52-53e2b7g9gf21` | `dotnet/samples/AGUIClientServer/AGUIDojoServer` |
| `b7762d10-e29b-4bb1-8b74-b6d69a667dd4` | All Durable Task samples and tests |

## Integration Test Configuration System

Integration tests use a standardized configuration system:

### Configuration Classes

Tests under `dotnet/tests/AgentConformance.IntegrationTests/Support/` define configuration classes that map to configuration sections:

1. **OpenAIConfiguration**
   - `ServiceId` (string, optional)
   - `ChatModelId` (string)
   - `ChatReasoningModelId` (string)
   - `ApiKey` (string)

2. **AzureAIConfiguration**
   - `Endpoint` (string)
   - `DeploymentName` (string)
   - `BingConnectionId` (string)

3. **AnthropicConfiguration**
   - `ServiceId` (string, optional)
   - `ChatModelId` (string)
   - `ChatReasoningModelId` (string)
   - `ApiKey` (string)

4. **Mem0Configuration**
   - `ServiceUri` (string)
   - `ApiKey` (string)

5. **CopilotStudioAgentConfiguration** (in `dotnet/tests/CopilotStudio.IntegrationTests`)
   - `DirectConnectUrl` (string)
   - `TenantId` (string)
   - `AppClientId` (string)

### Configuration Loading Priority

The `TestConfiguration` class loads settings in this order (later sources override earlier ones):
1. `testsettings.json` (optional)
2. `testsettings.development.json` (optional)
3. Environment variables
4. User secrets

### Usage Pattern

Tests load configuration using:
```csharp
private static readonly XyzConfiguration s_config = TestConfiguration.LoadSection<XyzConfiguration>();
```

The section name is derived from the class name by removing the "Configuration" suffix.

## Summary Statistics

- **Total unique environment variables/secrets**: 54
- **Total sample projects analyzed**: 157
- **Total integration test projects analyzed**: 14
- **Configuration classes in tests**: 5

## Notes

1. Many samples provide default values for deployment names (e.g., "gpt-4o-mini", "claude-haiku-4-5")
2. Azure OpenAI samples generally use Managed Identity by default but support optional API key via `AZURE_OPENAI_KEY`
3. Durable Task samples use both `AZURE_OPENAI_DEPLOYMENT_NAME` and `AZURE_OPENAI_DEPLOYMENT` for backward compatibility
4. Configuration values can be provided via:
   - Environment variables (highest priority)
   - User secrets
   - `appsettings.json` / `appsettings.Development.json`
   - `testsettings.json` / `testsettings.development.json` (for tests)
5. Some configuration keys use IConfiguration indexer syntax (e.g., `Configuration["key"]`) which can read from any of the above sources
