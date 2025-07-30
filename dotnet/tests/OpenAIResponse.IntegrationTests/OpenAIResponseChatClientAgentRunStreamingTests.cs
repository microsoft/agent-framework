// Copyright (c) Microsoft. All rights reserved.

using AgentConformance.IntegrationTests;

namespace OpenAIResponse.IntegrationTests;

public class OpenAIResponseStoreTrueChatClientAgentRunStreamingTests() : ChatClientAgentRunStreamingTests<OpenAIResponseFixture>(() => new(store: true))
{
}

public class OpenAIResponseStoreFalseChatClientAgentRunStreamingTests() : ChatClientAgentRunStreamingTests<OpenAIResponseFixture>(() => new(store: false))
{
}
