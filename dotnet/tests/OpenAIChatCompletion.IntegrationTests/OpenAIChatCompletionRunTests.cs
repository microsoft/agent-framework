// Copyright (c) Microsoft. All rights reserved.

using AgentConformance.IntegrationTests;

namespace OpenAIChatCompletion.IntegrationTests;

public class OpenAIChatCompletionRunTests()
    : RunTests<OpenAIChatCompletionFixture>(() => new(useReasoningChatModel: false))
{
}

public class OpenAIChatCompletionReasoningRunTests()
    : RunTests<OpenAIChatCompletionFixture>(() => new(useReasoningChatModel: true))
{
}
