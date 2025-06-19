// Copyright (c) Microsoft. All rights reserved.

using AgentConformance.IntegrationTests;

namespace OpenAIAssistant.IntegrationTests;

public class OpenAIAssistantChatClientAgentRunStreamingTests() : ChatClientAgentRunStreamingTests<OpenAIAssistantFixture>(() => new())
{
}
