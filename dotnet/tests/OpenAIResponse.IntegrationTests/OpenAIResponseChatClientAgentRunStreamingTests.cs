// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using AgentConformance.IntegrationTests;

namespace ResponseResult.IntegrationTests;

public class OpenAIResponseStoreTrueChatClientAgentRunStreamingTests() : ChatClientAgentRunStreamingTests<OpenAIResponseFixture>(() => new(store: true))
{
    private const string SkipReason = "ResponseResult does not support empty messages";

    public override Task RunWithInstructionsAndNoMessageReturnsExpectedResultAsync()
    {
        Assert.Skip(SkipReason);
        return base.RunWithInstructionsAndNoMessageReturnsExpectedResultAsync();
    }
}

public class OpenAIResponseStoreFalseChatClientAgentRunStreamingTests() : ChatClientAgentRunStreamingTests<OpenAIResponseFixture>(() => new(store: false))
{
    private const string SkipReason = "ResponseResult does not support empty messages";

    public override Task RunWithInstructionsAndNoMessageReturnsExpectedResultAsync()
    {
        Assert.Skip(SkipReason);
        return base.RunWithInstructionsAndNoMessageReturnsExpectedResultAsync();
    }
}
