// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

public class AggregatingExecutorTests
{
    [Fact]
    public async Task AggregatingExecutor_HandleAsync_AggregatesIncrementallyAsync()
    {
        AggregatingExecutor<string, string> executor = new("sum", (aggregate, input) =>
            aggregate == null ? input : $"{aggregate}+{input}");

        TestWorkflowContext context = new(executor.Id);

        string? result1 = await executor.HandleAsync("a", context, default);
        string? result2 = await executor.HandleAsync("b", context, default);
        string? result3 = await executor.HandleAsync("c", context, default);

        Assert.Equal("a", result1);
        Assert.Equal("a+b", result2);
        Assert.Equal("a+b+c", result3);
    }

    [Fact]
    public async Task AggregatingExecutor_HandleAsync_FirstCallReceivesNullAggregateAsync()
    {
        string? receivedAggregate = "sentinel";

        AggregatingExecutor<string, string> executor = new("first-call", (aggregate, input) =>
        {
            receivedAggregate = aggregate;
            return input;
        });

        TestWorkflowContext context = new(executor.Id);
        await executor.HandleAsync("hello", context, default);

        Assert.Null(receivedAggregate);
    }

    [Fact]
    public async Task AggregatingExecutor_HandleAsync_AggregatorReturningNullClearsStateAsync()
    {
        AggregatingExecutor<string, string> executor = new("nullable", (aggregate, input) =>
            input == "clear" ? null : (aggregate ?? "") + input);

        TestWorkflowContext context = new(executor.Id);

        string? result1 = await executor.HandleAsync("a", context, default);
        Assert.Equal("a", result1);

        string? result2 = await executor.HandleAsync("clear", context, default);
        Assert.Null(result2);

        // After clearing, the next call should receive null aggregate again
        string? result3 = await executor.HandleAsync("b", context, default);
        Assert.Equal("b", result3);
    }

    [Fact]
    public async Task AggregatingExecutor_HandleAsync_PersistsStateBetweenCallsAsync()
    {
        AggregatingExecutor<string, string> executor = new("counter", (aggregate, _) =>
            aggregate == null ? "1" : $"{int.Parse(aggregate) + 1}");

        TestWorkflowContext context = new(executor.Id);

        for (int i = 1; i <= 5; i++)
        {
            string? result = await executor.HandleAsync("tick", context, default);
            Assert.Equal($"{i}", result);
        }
    }
}
