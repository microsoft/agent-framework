// Copyright (c) Microsoft. All rights reserved.

using AgentConformance.IntegrationTests;

namespace OpenAIResponse.IntegrationTests;

public class OpenAIResponseStoreTrueRunStreamingTests() : RunStreamingTests<OpenAIResponseFixture>(() => new(store: true))
{
}

public class OpenAIResponseStoreFalseRunStreamingTests() : RunStreamingTests<OpenAIResponseFixture>(() => new(store: false))
{
}
