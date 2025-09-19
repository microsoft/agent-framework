// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using AgentConformance.IntegrationTests;

namespace OpenAIResponse.IntegrationTests;

public class OpenAIResponseStoreTrueRunTests() : RunTests<OpenAIResponseFixture>(() => new(store: true))
{
    private const string SkipReason = "OpenAIResponse does not support empty messages";
    [Fact(Skip = SkipReason)]
    public override Task RunWithNoMessageDoesNotFailAsync() =>
        Task.CompletedTask;
}

public class OpenAIResponseStoreFalseRunTests() : RunTests<OpenAIResponseFixture>(() => new(store: false))
{
    private const string SkipReason = "OpenAIResponse does not support empty messages";

    [Fact(Skip = SkipReason)]
    public override Task RunWithNoMessageDoesNotFailAsync() =>
        Task.CompletedTask;
}
