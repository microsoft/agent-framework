// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using AgentConformance.IntegrationTests;

namespace OpenAIChatCompletion.IntegrationTests;

public class OpenAIChatCompletionChatClientAgentRunStreamingTests()
    : ChatClientAgentRunStreamingTests<OpenAIChatCompletionFixture>(() => new(useReasoningChatModel: false))
{
}

public class OpenAIChatCompletionChatClientAgentReasoningRunStreamingTests()
    : ChatClientAgentRunStreamingTests<OpenAIChatCompletionFixture>(() => new(useReasoningChatModel: true))
{
    [Fact(Skip = "Image content is not supported for reasoning model")]
    public override Task RunWithImageContentWorksAsync()
    {
        return Task.CompletedTask;
    }
}
