// Copyright (c) Microsoft. All rights reserved.

using AgentConformance.IntegrationTests;

namespace OpenAIResponse.IntegrationTests;

public class OpenAIResponseStoreTrueInvokeTests() : RunAsyncTests<OpenAIResponseFixture>(() => new(store: true))
{
}

public class OpenAIResponseStoreFalseInvokeTests() : RunAsyncTests<OpenAIResponseFixture>(() => new(store: false))
{
}
