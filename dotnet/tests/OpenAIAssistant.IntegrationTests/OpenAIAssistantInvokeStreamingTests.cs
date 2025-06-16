// Copyright (c) Microsoft. All rights reserved.

using AgentConformance.IntegrationTests;

namespace OpenAIAssistant.IntegrationTests;

public class OpenAIAssistantInvokeStreamingTests() : RunStreamingAsyncTests<OpenAIAssistantFixture>(() => new())
{
}
