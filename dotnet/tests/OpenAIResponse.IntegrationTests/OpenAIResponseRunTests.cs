// Copyright (c) Microsoft. All rights reserved.

using AgentConformance.IntegrationTests;

namespace OpenAIResponse.IntegrationTests;

public class OpenAIResponseStoreTrueRunTests() : RunTests<OpenAIResponseFixture>(() => new(store: true))
{
}

public class OpenAIResponseStoreFalseRunTests() : RunTests<OpenAIResponseFixture>(() => new(store: false))
{
}
