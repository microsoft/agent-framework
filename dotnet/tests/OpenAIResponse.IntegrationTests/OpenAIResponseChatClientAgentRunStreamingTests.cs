// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using AgentConformance.IntegrationTests;

namespace OpenAIResponse.IntegrationTests;

public class OpenAIResponseStoreTrueChatClientAgentRunStreamingTests() : ChatClientAgentRunStreamingTests<OpenAIResponseFixture>(() => new(store: true))
{
    private const string SkipReason = "OpenAIResponse does not support empty messages";

    [Fact(Skip = SkipReason)]
    public override Task RunWithInstructionsAndNoMessageReturnsExpectedResultAsync() =>
        Task.CompletedTask;
}

public class OpenAIResponseStoreFalseChatClientAgentRunStreamingTests() : ChatClientAgentRunStreamingTests<OpenAIResponseFixture>(() => new(store: false))
{
    private const string SkipReason = "OpenAIResponse does not support empty messages";

    [Fact(Skip = SkipReason)]
    public override Task RunWithInstructionsAndNoMessageReturnsExpectedResultAsync() =>
        Task.CompletedTask;
}
