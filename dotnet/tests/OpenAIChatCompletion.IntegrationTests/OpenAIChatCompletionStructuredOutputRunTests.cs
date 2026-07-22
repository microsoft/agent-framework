// Copyright (c) Microsoft. All rights reserved.

using AgentConformance.IntegrationTests;

namespace OpenAIChatCompletion.IntegrationTests;

public class OpenAIChatCompletionStructuredOutputRunTests() : StructuredOutputRunTests<OpenAIChatCompletionFixture>(() => new(useReasoningChatModel: false))
{
}
