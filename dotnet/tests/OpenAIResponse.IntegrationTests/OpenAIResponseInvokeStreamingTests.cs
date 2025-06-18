// Copyright (c) Microsoft. All rights reserved.

using AgentConformance.IntegrationTests;

namespace OpenAIResponse.IntegrationTests;

public class OpenAIResponseStoreTrueInvokeStreamingTests() : RunStreamingAsyncTests<OpenAIResponseFixture>(() => new(store: true))
{
}

public class OpenAIResponseStoreFalseInvokeStreamingTests() : RunStreamingAsyncTests<OpenAIResponseFixture>(() => new(store: false))
{
}
