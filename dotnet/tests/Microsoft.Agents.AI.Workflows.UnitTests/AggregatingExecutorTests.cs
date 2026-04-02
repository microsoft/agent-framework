// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using FluentAssertions;

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

        result1.Should().Be("a");
        result2.Should().Be("a+b");
        result3.Should().Be("a+b+c");
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

        receivedAggregate.Should().BeNull("the first invocation should receive a null aggregate for reference types");
    }

    [Fact]
    public async Task AggregatingExecutor_HandleAsync_AggregatorReturningNullClearsStateAsync()
    {
        AggregatingExecutor<string, string> executor = new("nullable", (aggregate, input) =>
            input == "clear" ? null : (aggregate ?? "") + input);

        TestWorkflowContext context = new(executor.Id);

        string? result1 = await executor.HandleAsync("a", context, default);
        result1.Should().Be("a");

        string? result2 = await executor.HandleAsync("clear", context, default);
        result2.Should().BeNull("the aggregator returned null to clear the state");

        // After clearing, the next call should receive null aggregate again
        string? result3 = await executor.HandleAsync("b", context, default);
        result3.Should().Be("b", "the aggregate should restart from null after being cleared");
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
            result.Should().Be($"{i}", "the aggregate should increment with each call");
        }
    }
}
