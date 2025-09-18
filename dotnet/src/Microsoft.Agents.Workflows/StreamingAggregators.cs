// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;

namespace Microsoft.Agents.Workflows;

/// <summary>
/// Represents a function that incrementally aggregates a sequence of input values, producing an updated result for each
/// input.
/// </summary>
/// <typeparam name="TInput">The type of the input value to be aggregated.</typeparam>
/// <typeparam name="TResult">The type of the aggregation result produced by the function.</typeparam>
/// <param name="input">The current input value to be incorporated into the aggregation.</param>
/// <param name="runningResult">The current aggregated result, or null if this is the first input.</param>
/// <returns>The updated aggregation result after processing the input value, or null if no result can be produced.</returns>
public delegate TResult? StreamingAggregator<in TInput, TResult>(TInput input, TResult? runningResult);

/// <summary>
/// Provides a set of streaming aggregation functions for processing sequences of input values in a stateful,
/// incremental manner.
/// </summary>
public static class StreamingAggregators
{
    /// <summary>
    /// Creates a streaming aggregator that returns the result of applying the specified conversion function to the
    /// first input value.
    /// </summary>
    /// <remarks>Subsequent inputs after the first are ignored by the aggregator. This method is useful for
    /// scenarios where only the first occurrence in a stream is relevant. The conversion function is invoked at most
    /// once.</remarks>
    /// <typeparam name="TInput">The type of the input elements to be aggregated.</typeparam>
    /// <typeparam name="TResult">The type of the result produced by the conversion function.</typeparam>
    /// <param name="conversion">A function that converts an input value of type <typeparamref name="TInput"/> to a result of type <typeparamref
    /// name="TResult"/>. This function is applied to the first input received.</param>
    /// <returns>A <see cref="StreamingAggregator{TInput, TResult}"/> that yields the converted result of the first input.</returns>
    public static StreamingAggregator<TInput, TResult> First<TInput, TResult>(Func<TInput, TResult> conversion)
    {
        bool hasRun = false;
        TResult? local = default;

        return Aggregate;

        TResult? Aggregate(TInput input, TResult? runningResult)
        {
            if (!hasRun)
            {
                local = conversion(input);
                hasRun = true;
            }

            return local;
        }
    }

    /// <summary>
    /// Creates a streaming aggregator that returns the first input element.
    /// </summary>
    /// <typeparam name="TInput">The type of the input elements to aggregate.</typeparam>
    /// <returns>A <see cref="StreamingAggregator{TInput, TInput}"/> that yields the first input element.</returns>
    public static StreamingAggregator<TInput, TInput> First<TInput>() => First<TInput, TInput>(input => input);

    /// <summary>
    /// Creates a streaming aggregator that returns the result of applying the specified conversion to the most recent
    /// input value.
    /// </summary>
    /// <typeparam name="TInput">The type of the input elements to be aggregated.</typeparam>
    /// <typeparam name="TResult">The type of the result produced by the conversion function.</typeparam>
    /// <param name="conversion">A function that converts each input value to a result. Cannot be null.</param>
    /// <returns>A streaming aggregator that yields the converted value of the last input received.</returns>
    public static StreamingAggregator<TInput, TResult> Last<TInput, TResult>(Func<TInput, TResult> conversion)
    {
        TResult? local = default;

        return Aggregate;

        TResult? Aggregate(TInput input, TResult? runningResult)
        {
            local = conversion(input);
            return local;
        }
    }

    /// <summary>
    /// Creates a streaming aggregator that returns the last element in a sequence.
    /// </summary>
    /// <typeparam name="TInput">The type of elements in the input sequence.</typeparam>
    /// <returns>A <see cref="StreamingAggregator{TInput, TInput}"/> that yields the last element of the sequence.</returns>
    public static StreamingAggregator<TInput, TInput> Last<TInput>() => Last<TInput, TInput>(input => input);

    /// <summary>
    /// Creates a streaming aggregator that produces the union of results by applying a conversion function to each
    /// input and accumulating the results.
    /// </summary>
    /// <typeparam name="TInput">The type of the input elements to be aggregated.</typeparam>
    /// <typeparam name="TResult">The type of the result elements produced by the conversion function.</typeparam>
    /// <param name="conversion">A function that converts each input element to a result element to be included in the union.</param>
    /// <returns>A streaming aggregator that, for each input, returns an enumerable containing all result elements produced so
    /// far.</returns>
    public static StreamingAggregator<TInput, IEnumerable<TResult>> Union<TInput, TResult>(Func<TInput, TResult> conversion)
    {
        return Aggregate;

        IEnumerable<TResult> Aggregate(TInput input, IEnumerable<TResult>? runningResult)
        {
            return runningResult is not null ? runningResult.Append(conversion(input)) : [conversion(input)];
        }
    }

    /// <summary>
    /// Creates a streaming aggregator that produces the union of all input sequences of type TInput.
    /// </summary>
    /// <remarks>The resulting aggregator combines all input sequences into a single sequence containing
    /// distinct elements. The order of elements in the output sequence is not guaranteed.</remarks>
    /// <typeparam name="TInput">The type of the elements in the input sequences to be aggregated.</typeparam>
    /// <returns>A StreamingAggregator that, when applied to multiple input sequences, returns an IEnumerable containing the
    /// union of all elements from those sequences.</returns>
    public static StreamingAggregator<TInput, IEnumerable<TInput>> Union<TInput>()
    {
        return Aggregate;

        static IEnumerable<TInput> Aggregate(TInput input, IEnumerable<TInput>? runningResult)
        {
            return runningResult is not null ? runningResult.Append(input) : [input];
        }
    }
}
