// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;

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
    /// first input value, or a default value if no input is provided.
    /// </summary>
    /// <remarks>Subsequent inputs after the first are ignored by the aggregator. This method is useful for
    /// scenarios where only the first occurrence in a stream is relevant. The conversion function is invoked at most
    /// once.</remarks>
    /// <typeparam name="TInput">The type of the input elements to be aggregated.</typeparam>
    /// <typeparam name="TResult">The type of the result produced by the conversion function.</typeparam>
    /// <param name="conversion">A function that converts an input value of type <typeparamref name="TInput"/> to a result of type <typeparamref
    /// name="TResult"/>. This function is applied to the first input received.</param>
    /// <param name="defaultValue">The value to return if no input is provided. </param>
    /// <returns>A <see cref="StreamingAggregator{TInput, TResult}"/> that yields the converted result of the first input, or the
    /// specified default value if no input is received.</returns>
    public static StreamingAggregator<TInput, TResult> First<TInput, TResult>(Func<TInput, TResult> conversion, TResult? defaultValue = default)
    {
        bool hasRun = false;
        TResult? local = defaultValue;

        return Aggregate;

        TResult? Aggregate(TInput input, TResult? runningResult)
        {
            if (!hasRun)
            {
                local = conversion(input);
            }

            return local;
        }
    }

    /// <summary>
    /// Creates a streaming aggregator that returns the first input element, or a specified default value if no elements
    /// are provided.
    /// </summary>
    /// <typeparam name="TInput">The type of the input elements to aggregate.</typeparam>
    /// <param name="defaultValue">The value to return if the input sequence contains no elements.</param>
    /// <returns>A <see cref="StreamingAggregator{TInput, TInput}"/> that yields the first input element, or <paramref
    /// name="defaultValue"/> if the sequence is empty.</returns>
    public static StreamingAggregator<TInput, TInput> First<TInput>(TInput? defaultValue = default)
        => First<TInput, TInput>(input => input, defaultValue);

    /// <summary>
    /// Creates a streaming aggregator that returns the result of applying the specified conversion to the most recent
    /// input value.
    /// </summary>
    /// <typeparam name="TInput">The type of the input elements to be aggregated.</typeparam>
    /// <typeparam name="TResult">The type of the result produced by the conversion function.</typeparam>
    /// <param name="conversion">A function that converts each input value to a result. Cannot be null.</param>
    /// <param name="defaultValue">The initial result value to use before any input is processed.</param>
    /// <returns>A streaming aggregator that yields the converted value of the last input received, or the specified default
    /// value if no input has been processed.</returns>
    public static StreamingAggregator<TInput, TResult> Last<TInput, TResult>(Func<TInput, TResult> conversion, TResult? defaultValue = default)
    {
        TResult? local = defaultValue;

        return Aggregate;

        TResult? Aggregate(TInput input, TResult? runningResult)
        {
            local = conversion(input);
            return local;
        }
    }

    /// <summary>
    /// Creates a streaming aggregator that returns the last element in a sequence, or a specified default value if the
    /// sequence is empty.
    /// </summary>
    /// <typeparam name="TInput">The type of elements in the input sequence.</typeparam>
    /// <param name="defaultValue">The value to return if the input sequence contains no elements.</param>
    /// <returns>A <see cref="StreamingAggregator{TInput, TInput}"/> that yields the last element of the sequence, or <paramref
    /// name="defaultValue"/> if the sequence is empty.</returns>
    public static StreamingAggregator<TInput, TInput> Last<TInput>(TInput? defaultValue = default)
        => Last<TInput, TInput>(input => input, defaultValue);

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
        List<TResult> results = new();

        return Aggregate;

        IEnumerable<TResult> Aggregate(TInput input, IEnumerable<TResult>? runningResult)
        {
            results.Add(conversion(input));
            return results;
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
        => Union<TInput, TInput>(input => input);
}
