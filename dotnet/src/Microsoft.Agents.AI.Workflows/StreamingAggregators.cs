// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;

namespace Microsoft.Agents.AI.Workflows;

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
    /// <param name="conversion">A function that converts an input value of type <typeparamref name="TInput"/> to a result
    /// of type <typeparamref name="TResult"/>. This function is applied to the first input received.</param>
    /// <returns>An aggregation function that yields the result of converting the first input using the specified function.</returns>
    public static Func<TResult?, TInput, TResult?> First<TInput, TResult>(Func<TInput, TResult> conversion)
    {
        return Aggregate;

        TResult? Aggregate(TResult? runningResult, TInput input)
        {
            runningResult ??= conversion(input);
            return runningResult;
        }
    }

    /// <summary>
    /// Creates a streaming aggregator that returns the first input element.
    /// </summary>
    /// <typeparam name="TInput">The type of the input elements to aggregate.</typeparam>
    /// <returns>A an aggrgation function that yields the first input element.</returns>
    public static Func<TInput?, TInput, TInput?> First<TInput>() => First<TInput, TInput?>(input => input);

    /// <summary>
    /// Creates a streaming aggregator that returns the result of applying the specified conversion to the most recent
    /// input value.
    /// </summary>
    /// <typeparam name="TInput">The type of the input elements to be aggregated.</typeparam>
    /// <typeparam name="TResult">The type of the result produced by the conversion function.</typeparam>
    /// <param name="conversion">A function that converts each input value to a result. Cannot be null.</param>
    /// <returns>A aggregator function that yields the  result of converting the last input received using the specified
    /// function.</returns>
    public static Func<TResult?, TInput, TResult?> Last<TInput, TResult>(Func<TInput, TResult> conversion)
    {
        return Aggregate;

        TResult? Aggregate(TResult? runningResult, TInput input)
        {
            return conversion(input);
        }
    }

    /// <summary>
    /// Creates a streaming aggregator that returns the last element in a sequence.
    /// </summary>
    /// <typeparam name="TInput">The type of elements in the input sequence.</typeparam>
    /// <returns>An aggregator function that yields the last element of the input.</returns>
    public static Func<TInput?, TInput, TInput?> Last<TInput>() => Last<TInput, TInput?>(input => input);

    /// <summary>
    /// Creates a streaming aggregator that produces the union of results by applying a conversion function to each
    /// input and accumulating the results.
    /// </summary>
    /// <typeparam name="TInput">The type of the input elements to be aggregated.</typeparam>
    /// <typeparam name="TResult">The type of the result elements produced by the conversion function.</typeparam>
    /// <param name="conversion">A function that converts each input element to a result element to be included in the union.</param>
    /// <returns>An aggregator function that, for each input, returns an enumerable containing the result of converting every
    /// element produced so far.</returns>
    public static Func<IEnumerable<TResult>?, TInput, IEnumerable<TResult>?> Union<TInput, TResult>(Func<TInput, TResult> conversion)
    {
        return Aggregate;

        IEnumerable<TResult> Aggregate(IEnumerable<TResult>? runningResult, TInput input)
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
    /// <returns>An aggregator function, that, when applied to multiple input sequences, returns an <see cref="IEnumerable{TInput}"/>
    /// containing the union of all elements from those sequences.</returns>
    public static Func<IEnumerable<TInput>?, TInput, IEnumerable<TInput>?> Union<TInput>()
    {
        return Aggregate;

        static IEnumerable<TInput> Aggregate(IEnumerable<TInput>? runningResult, TInput input)
        {
            return runningResult is not null ? runningResult.Append(input) : [input];
        }
    }
}
