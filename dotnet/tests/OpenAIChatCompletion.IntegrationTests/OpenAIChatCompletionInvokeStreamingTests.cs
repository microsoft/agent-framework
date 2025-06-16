// Copyright (c) Microsoft. All rights reserved.

using AgentConformance.IntegrationTests;

namespace OpenAIChatCompletion.IntegrationTests;

public class OpenAIChatCompletionInvokeStreamingTests() : RunStreamingAsyncTests<OpenAIChatCompletionFixture>(() => new())
{
}
