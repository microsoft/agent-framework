// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using FluentAssertions;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

public class StreamingAggregatorsTests
{
    private static TResult? ApplyStreamingAggregator<TInput, TResult>(
        Func<TResult?, TInput, TResult?> aggregator,
        IEnumerable<TInput> inputs,
        TResult? runningResult = default)
    {
        foreach (TInput input in inputs)
        {
            runningResult = aggregator(runningResult, input);
        }

        return runningResult!;
    }

    [Fact]
    public void Test_StreamingAggregators_First()
    {
        IEnumerable<int?> inputs = [1, 2, 3];
        Func<int?, int?, int?> aggregator = StreamingAggregators.First<int?>();

        int? runningResult = ApplyStreamingAggregator(aggregator, inputs);
        runningResult.Should().Be(1);

        // Ensure that subsequent inputs do not change the result
        ApplyStreamingAggregator(aggregator, inputs.Skip(1), runningResult.Value)
            .Should()
            .Be(1, "subsequent inputs should not change the result of First aggregator");
    }

    [Fact]
    public void Test_StreamingAggregators_First_WithConversion()
    {
        IEnumerable<int?> inputs = [2, 4, 6];
        Func<int?, int?, int?> aggregator = StreamingAggregators.First<int?, int?>(input => input / 2);

        int? runningResult = ApplyStreamingAggregator(aggregator, inputs);
        runningResult.Should().Be(1);

        // Ensure that subsequent inputs do not change the result
        ApplyStreamingAggregator(aggregator, inputs.Skip(1), runningResult.Value)
            .Should()
            .Be(1, "subsequent inputs should not change the result of First aggregator with conversion");
    }

    [Fact]
    public void Test_StreamingAggregators_Last()
    {
        IEnumerable<int> inputs = [1, 2, 3];
        Func<int, int, int> aggregator = StreamingAggregators.Last<int>();

        int? runningResult = ApplyStreamingAggregator(aggregator, inputs);
        runningResult.Should().Be(3);

        // Ensure that subsequent inputs do change the result
        ApplyStreamingAggregator(aggregator, inputs.Take(2), runningResult.Value)
            .Should()
            .Be(2, "subsequent inputs should change the result of Last aggregator");
    }

    [Fact]
    public void Test_StreamingAggregators_Last_WithConversion()
    {
        IEnumerable<int> inputs = [2, 4, 6];
        Func<int, int, int> aggregator = StreamingAggregators.Last<int, int>(input => input / 2);

        int? runningResult = ApplyStreamingAggregator(aggregator, inputs);
        runningResult.Should().Be(3);

        // Ensure that subsequent inputs do change the result
        ApplyStreamingAggregator(aggregator, inputs.Take(2), runningResult.Value)
            .Should()
            .Be(2, "subsequent inputs should change the result of Last aggregator");
    }

    [Fact]
    public void Test_StreamingAggregators_Union()
    {
        IEnumerable<int> inputs = [1, 2, 3];
        Func<IEnumerable<int>?, int, IEnumerable<int>?> aggregator = StreamingAggregators.Union<int>();

        IEnumerable<int>? runningResult = ApplyStreamingAggregator(aggregator, inputs);
        runningResult.Should().BeEquivalentTo([1, 2, 3], "Union should accumulate all inputs in order");

        // Ensure that subsequent inputs concatenate to the existing results
        inputs = [4, 5];

        ApplyStreamingAggregator(aggregator, inputs, runningResult)
            .Should()
            .BeEquivalentTo([1, 2, 3, 4, 5], "Union should accumulate all inputs in order including subsequent inputs");
    }

    [Fact]
    public void Test_StreamingAggregators_Union_WithConversion()
    {
        IEnumerable<int> inputs = [2, 4, 6];
        Func<IEnumerable<int>?, int, IEnumerable<int>?> aggregator = StreamingAggregators.Union<int, int>(input => input / 2);

        IEnumerable<int>? runningResult = ApplyStreamingAggregator(aggregator, inputs);
        runningResult.Should().BeEquivalentTo([1, 2, 3],
            "Union with conversion should accumulate all converted inputs in order");

        // Ensure that subsequent inputs concatenate to the existing results
        inputs = [8, 10];
        ApplyStreamingAggregator(aggregator, inputs, runningResult)
            .Should()
            .BeEquivalentTo([1, 2, 3, 4, 5],
                "Union with conversion should accumulate all converted inputs in order including subsequent inputs");
    }
}
