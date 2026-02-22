// Copyright (c) Microsoft. All rights reserved.

namespace Shared.IntegrationTests;

/// <summary>
/// Constants for integration test configuration keys.
/// Values are resolved from environment variables and user secrets.
/// </summary>
internal static class TestSettings
{
    // Anthropic
    public const string AnthropicApiKey = "ANTHROPIC_API_KEY";
    public const string AnthropicChatModelName = "ANTHROPIC_CHAT_MODEL_NAME";
    public const string AnthropicReasoningModelName = "ANTHROPIC_REASONING_MODEL_NAME";
    public const string AnthropicServiceId = "ANTHROPIC_SERVICE_ID";

    // Azure AI (Foundry)
    public const string AzureAIBingConnectionId = "AZURE_AI_BING_CONNECTION_ID";
    public const string AzureAIMemoryStoreId = "AZURE_AI_MEMORY_STORE_ID";
    public const string AzureAIModelDeploymentName = "AZURE_AI_MODEL_DEPLOYMENT_NAME";
    public const string AzureAIProjectEndpoint = "AZURE_AI_PROJECT_ENDPOINT";

    // Copilot Studio
    public const string CopilotStudioAgentAppId = "COPILOTSTUDIO_AGENT_APP_ID";
    public const string CopilotStudioDirectConnectUrl = "COPILOTSTUDIO_DIRECT_CONNECT_URL";
    public const string CopilotStudioTenantId = "COPILOTSTUDIO_TENANT_ID";

    // Mem0
    public const string Mem0ApiKey = "MEM0_API_KEY";
    public const string Mem0Endpoint = "MEM0_ENDPOINT";

    // OpenAI
    public const string OpenAIApiKey = "OPENAI_API_KEY";
    public const string OpenAIChatModelName = "OPENAI_CHAT_MODEL_NAME";
    public const string OpenAIReasoningModelName = "OPENAI_REASONING_MODEL_NAME";
    public const string OpenAIServiceId = "OPENAI_SERVICE_ID";
}
