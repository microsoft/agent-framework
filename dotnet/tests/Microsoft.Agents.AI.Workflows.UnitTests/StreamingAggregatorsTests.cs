// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

public class StreamingAggregatorsTests
{
    private static readonly int[] s_expectedUnion = [1, 2, 3];
    private static readonly int[] s_expectedAppendedUnion = [1, 2, 3, 4, 5];

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
        Assert.Equal(1, runningResult);
        int runningValue = runningResult.GetValueOrDefault();

        // Ensure that subsequent inputs do not change the result
        Assert.Equal(1, ApplyStreamingAggregator(aggregator, inputs.Skip(1), runningValue));
    }

    [Fact]
    public void Test_StreamingAggregators_First_WithConversion()
    {
        IEnumerable<int?> inputs = [2, 4, 6];
        Func<int?, int?, int?> aggregator = StreamingAggregators.First<int?, int?>(input => input / 2);

        int? runningResult = ApplyStreamingAggregator(aggregator, inputs);
        Assert.Equal(1, runningResult);
        int runningValue = runningResult.GetValueOrDefault();

        // Ensure that subsequent inputs do not change the result
        Assert.Equal(1, ApplyStreamingAggregator(aggregator, inputs.Skip(1), runningValue));
    }

    [Fact]
    public void Test_StreamingAggregators_Last()
    {
        IEnumerable<int> inputs = [1, 2, 3];
        Func<int, int, int> aggregator = StreamingAggregators.Last<int>();

        int? runningResult = ApplyStreamingAggregator(aggregator, inputs);
        Assert.Equal(3, runningResult);

        // Ensure that subsequent inputs do change the result
        Assert.Equal(2, ApplyStreamingAggregator(aggregator, inputs.Take(2), runningResult.Value));
    }

    [Fact]
    public void Test_StreamingAggregators_Last_WithConversion()
    {
        IEnumerable<int> inputs = [2, 4, 6];
        Func<int, int, int> aggregator = StreamingAggregators.Last<int, int>(input => input / 2);

        int? runningResult = ApplyStreamingAggregator(aggregator, inputs);
        Assert.Equal(3, runningResult);

        // Ensure that subsequent inputs do change the result
        Assert.Equal(2, ApplyStreamingAggregator(aggregator, inputs.Take(2), runningResult.Value));
    }

    [Fact]
    public void Test_StreamingAggregators_Union()
    {
        IEnumerable<int> inputs = [1, 2, 3];
        Func<IEnumerable<int>?, int, IEnumerable<int>?> aggregator = StreamingAggregators.Union<int>();

        IEnumerable<int>? runningResult = ApplyStreamingAggregator(aggregator, inputs);
        Assert.Equivalent(s_expectedUnion, runningResult);

        // Ensure that subsequent inputs concatenate to the existing results
        inputs = [4, 5];

        Assert.Equivalent(s_expectedAppendedUnion, ApplyStreamingAggregator(aggregator, inputs, runningResult));
    }

    [Fact]
    public void Test_StreamingAggregators_Union_WithConversion()
    {
        IEnumerable<int> inputs = [2, 4, 6];
        Func<IEnumerable<int>?, int, IEnumerable<int>?> aggregator = StreamingAggregators.Union<int, int>(input => input / 2);

        IEnumerable<int>? runningResult = ApplyStreamingAggregator(aggregator, inputs);
        Assert.Equivalent(s_expectedUnion, runningResult);

        // Ensure that subsequent inputs concatenate to the existing results
        inputs = [8, 10];
        Assert.Equivalent(s_expectedAppendedUnion, ApplyStreamingAggregator(aggregator, inputs, runningResult));
    }
}
