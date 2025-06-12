// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;
using Microsoft.Shared.Samples;
using OpenAI;

namespace GettingStarted;

public class AgentSample(ITestOutputHelper output) : BaseSample(output)
{
    protected IChatClient GetOpenAIChatClient()
        => new OpenAIClient(TestConfiguration.OpenAI.ApiKey)
            .GetChatClient(TestConfiguration.OpenAI.ChatModelId)
            .AsIChatClient();
}
