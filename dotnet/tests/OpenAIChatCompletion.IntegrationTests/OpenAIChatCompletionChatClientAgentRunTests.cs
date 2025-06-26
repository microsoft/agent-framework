// Copyright (c) Microsoft. All rights reserved.

using AgentConformance.IntegrationTests;

namespace OpenAIChatCompletion.IntegrationTests;

public class OpenAIChatCompletionChatClientAgentRunTests()
    : ChatClientAgentRunTests<OpenAIChatCompletionFixture>(() => new(useReasoningChatModel: false))
{
}

public class OpenAIChatCompletionChatClientAgentReasoningRunTests()
    : ChatClientAgentRunTests<OpenAIChatCompletionFixture>(() => new(useReasoningChatModel: true))
{
}
