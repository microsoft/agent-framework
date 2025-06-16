﻿// Copyright (c) Microsoft. All rights reserved.

using AgentConformance.IntegrationTests;

namespace OpenAIChatCompletion.IntegrationTests;

public class OpenAIAssistantInvokeStreamingTests() : RunStreamingAsyncTests<OpenAIAssistantFixture>(() => new())
{
}
