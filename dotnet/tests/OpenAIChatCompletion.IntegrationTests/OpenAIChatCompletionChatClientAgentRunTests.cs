// Copyright (c) Microsoft. All rights reserved.

using AgentConformance.IntegrationTests;

namespace OpenAIChatCompletion.IntegrationTests;

public class OpenAIChatCompletionChatClientAgentRunTests() : ChatClientAgentRunTests<OpenAIChatCompletionFixture>(() => new())
{
}
