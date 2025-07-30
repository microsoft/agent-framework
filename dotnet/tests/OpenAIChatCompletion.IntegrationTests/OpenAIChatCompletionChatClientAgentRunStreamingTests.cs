// Copyright (c) Microsoft. All rights reserved.

using AgentConformance.IntegrationTests;

namespace OpenAIChatCompletion.IntegrationTests;

public class OpenAIChatCompletionChatClientAgentRunStreamingTests()
    : ChatClientAgentRunStreamingTests<OpenAIChatCompletionFixture>(() => new(useReasoningChatModel: false))
{
}

public class OpenAIChatCompletionChatClientAgentReasoningRunStreamingTests()
    : ChatClientAgentRunStreamingTests<OpenAIChatCompletionFixture>(() => new(useReasoningChatModel: true))
{
}
