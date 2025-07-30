// Copyright (c) Microsoft. All rights reserved.

using AgentConformance.IntegrationTests;

namespace OpenAIChatCompletion.IntegrationTests;

public class OpenAIChatCompletionRunStreamingTests()
    : RunStreamingTests<OpenAIChatCompletionFixture>(() => new(useReasoningChatModel: false))
{
}

public class OpenAIChatCompletionReasoningRunStreamingTests()
    : RunStreamingTests<OpenAIChatCompletionFixture>(() => new(useReasoningChatModel: true))
{
}
