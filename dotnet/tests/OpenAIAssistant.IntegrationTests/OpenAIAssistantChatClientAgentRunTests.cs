// Copyright (c) Microsoft. All rights reserved.

using AgentConformance.IntegrationTests;

namespace OpenAIAssistant.IntegrationTests;

public class OpenAIAssistantChatClientAgentRunTests() : ChatClientAgentRunTests<OpenAIAssistantFixture>(() => new())
{
}
