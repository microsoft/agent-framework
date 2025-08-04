// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;

namespace Microsoft.Agents.Workflows;

internal delegate TResult? StreamingAggregator<TInput, TResult>(TInput input);

internal static class StreamingAggregators
{
    public static StreamingAggregator<TInput, TResult> First<TInput, TResult>(Func<TInput, TResult> conversion, TResult? defaultValue = default)
    {
        bool hasRun = false;
        TResult? local = defaultValue;

        return Aggregate;

        TResult? Aggregate(TInput input)
        {
            if (!hasRun)
            {
                local = conversion(input);
            }

            return local;
        }
    }

    public static StreamingAggregator<TInput, TInput> First<TInput>(TInput? defaultValue = default)
        => First<TInput, TInput>(input => input, defaultValue);

    public static StreamingAggregator<TInput, TResult> Last<TInput, TResult>(Func<TInput, TResult> conversion, TResult? defaultValue = default)
    {
        TResult? local = defaultValue;

        return Aggregate;

        TResult? Aggregate(TInput input)
        {
            local = conversion(input);
            return local;
        }
    }

    public static StreamingAggregator<TInput, TInput> Last<TInput>(TInput? defaultValue = default)
        => Last<TInput, TInput>(input => input, defaultValue);

    public static StreamingAggregator<TInput, IEnumerable<TResult>> Union<TInput, TResult>(Func<TInput, TResult> conversion)
    {
        List<TResult> results = new();

        return Aggregate;

        IEnumerable<TResult> Aggregate(TInput input)
        {
            results.Add(conversion(input));
            return results;
        }
    }

    public static StreamingAggregator<TInput, IEnumerable<TInput>> Union<TInput>()
        => Union<TInput, TInput>(input => input);
}
