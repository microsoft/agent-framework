// Copyright (c) Microsoft. All rights reserved.

using AgentConformance.IntegrationTests;

namespace OpenAIResponse.IntegrationTests;

public class OpenAIResponseStoreTrueChatClientAgentRunTests() : ChatClientAgentRunTests<OpenAIResponseFixture>(() => new(store: true))
{
}

public class OpenAIResponseStoreFalseChatClientAgentRunTests() : ChatClientAgentRunTests<OpenAIResponseFixture>(() => new(store: false))
{
}
