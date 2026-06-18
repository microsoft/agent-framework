// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using AgentConformance.IntegrationTests;

namespace ResponseResult.IntegrationTests;

public class OpenAIResponseStoreTrueRunStreamingTests() : RunStreamingTests<OpenAIResponseFixture>(() => new(store: true))
{
    private const string SkipReason = "ResponseResult does not support empty messages";

    public override Task RunWithNoMessageDoesNotFailAsync()
    {
        Assert.Skip(SkipReason);
        return base.RunWithNoMessageDoesNotFailAsync();
    }
}

public class OpenAIResponseStoreFalseRunStreamingTests() : RunStreamingTests<OpenAIResponseFixture>(() => new(store: false))
{
    private const string SkipReason = "ResponseResult does not support empty messages";

    public override Task RunWithNoMessageDoesNotFailAsync()
    {
        Assert.Skip(SkipReason);
        return base.RunWithNoMessageDoesNotFailAsync();
    }
}
