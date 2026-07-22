// Copyright (c) Microsoft. All rights reserved.

using AgentConformance.IntegrationTests;

namespace ResponseResult.IntegrationTests;

public class OpenAIResponseStructuredOutputRunTests() : StructuredOutputRunTests<OpenAIResponseFixture>(() => new(store: false))
{
}
