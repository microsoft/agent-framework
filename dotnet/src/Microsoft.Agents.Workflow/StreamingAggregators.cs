// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;

namespace Microsoft.Agents.Workflows;

/// <summary>
/// .
/// </summary>
/// <typeparam name="TInput"></typeparam>
/// <typeparam name="TResult"></typeparam>
/// <param name="input"></param>
/// <returns></returns>
public delegate TResult? StreamingAggregator<TInput, TResult>(TInput input);

/// <summary>
/// .
/// </summary>
public static class StreamingAggregators
{
    /// <summary>
    /// .
    /// </summary>
    /// <typeparam name="TInput"></typeparam>
    /// <typeparam name="TResult"></typeparam>
    /// <param name="conversion"></param>
    /// <param name="defaultValue"></param>
    /// <returns></returns>
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

    /// <summary>
    /// .
    /// </summary>
    /// <typeparam name="TInput"></typeparam>
    /// <param name="defaultValue"></param>
    /// <returns></returns>
    public static StreamingAggregator<TInput, TInput> First<TInput>(TInput? defaultValue = default)
        => First<TInput, TInput>(input => input, defaultValue);

    /// <summary>
    /// .
    /// </summary>
    /// <typeparam name="TInput"></typeparam>
    /// <typeparam name="TResult"></typeparam>
    /// <param name="conversion"></param>
    /// <param name="defaultValue"></param>
    /// <returns></returns>
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

    /// <summary>
    /// .
    /// </summary>
    /// <typeparam name="TInput"></typeparam>
    /// <param name="defaultValue"></param>
    /// <returns></returns>
    public static StreamingAggregator<TInput, TInput> Last<TInput>(TInput? defaultValue = default)
        => Last<TInput, TInput>(input => input, defaultValue);

    /// <summary>
    /// .
    /// </summary>
    /// <typeparam name="TInput"></typeparam>
    /// <typeparam name="TResult"></typeparam>
    /// <param name="conversion"></param>
    /// <returns></returns>
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

    /// <summary>
    /// .
    /// </summary>
    /// <typeparam name="TInput"></typeparam>
    /// <returns></returns>
    public static StreamingAggregator<TInput, IEnumerable<TInput>> Union<TInput>()
        => Union<TInput, TInput>(input => input);
}
