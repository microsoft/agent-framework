// Copyright (c) Microsoft. All rights reserved.

using AgentConformance.IntegrationTests;

namespace AgentConformance.OpenAIChatCompletion.IntegrationTests;

public class OpenAIChatCompletionInvokeTests() : RunAsyncTests<OpenAIChatCompletionFixture>(() => new OpenAIChatCompletionFixture())
{
}
