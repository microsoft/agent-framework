// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows;

/// <summary>
/// Provides a builder for constructing a switch-like control flow that maps predicates to one or more executors.
/// Enables the configuration of case-based and default execution logic for dynamic input handling.
/// </summary>
public sealed class SwitchBuilder
{
    private readonly List<ExecutorIsh> _executors = [];
    private readonly Dictionary<string, int> _executorIndicies = [];
    private readonly List<(Func<object?, bool> Predicate, HashSet<int> OutgoingIndicies)> _caseMap = [];
    private readonly HashSet<int> _defaultIndicies = [];

    /// <summary>
    /// Adds a case to the switch builder that associates a predicate with one or more executors.
    /// </summary>
    /// <remarks>
    /// Cases are evaluated in the order they are added.
    /// </remarks>
    /// <param name="predicate">A function that determines whether the associated executors should be considered for execution. The function
    /// receives an input object and returns <see langword="true"/> to select the case; otherwise, <see
    /// langword="false"/>.</param>
    /// <param name="executors">One or more executors to associate with the predicate. Each executor will be invoked if the predicate matches.
    /// Cannot be null.</param>
    /// <returns>The current <see cref="SwitchBuilder"/> instance, allowing for method chaining.</returns>
    public SwitchBuilder AddCase<T>(Func<T?, bool> predicate, params ExecutorIsh[] executors)
    {
        Throw.IfNull(predicate);
        Throw.IfNull(executors);

        HashSet<int> indicies = [];

        foreach (ExecutorIsh executor in executors)
        {
            if (!this._executorIndicies.TryGetValue(executor.Id, out int index))
            {
                index = this._executors.Count;
                this._executors.Add(executor);
                this._executorIndicies[executor.Id] = index;
            }

            indicies.Add(index);
        }

        Func<object?, bool> casePredicate = WorkflowBuilder.CreateConditionFunc(predicate)!;
        this._caseMap.Add((casePredicate, indicies));

        return this;
    }

    /// <summary>
    /// Adds one or more executors to be used as the default case when no other predicates match.
    /// </summary>
    /// <param name="executors"></param>
    /// <returns></returns>
    public SwitchBuilder WithDefault(params ExecutorIsh[] executors)
    {
        Throw.IfNull(executors);

        foreach (ExecutorIsh executor in executors)
        {
            if (!this._executorIndicies.TryGetValue(executor.Id, out int index))
            {
                index = this._executors.Count;
                this._executors.Add(executor);
                this._executorIndicies[executor.Id] = index;
            }

            this._defaultIndicies.Add(index);
        }

        return this;
    }

    internal WorkflowBuilder ReduceToFanOut(WorkflowBuilder builder, ExecutorIsh source)
    {
        List<(Func<object?, bool> Predicate, HashSet<int> OutgoingIndicies)> caseMap = this._caseMap;
        HashSet<int> defaultIndicies = this._defaultIndicies;

        return builder.AddFanOutEdge<object>(source, CasePartitioner, [.. this._executors]);

        IEnumerable<int> CasePartitioner(object? input, int targetCount)
        {
            Debug.Assert(targetCount == this._executors.Count);

            for (int i = 0; i < caseMap.Count; i++)
            {
                (Func<object?, bool> predicate, HashSet<int> outgoingIndicies) = caseMap[i];
                if (predicate(input))
                {
                    return outgoingIndicies;
                }
            }

            return defaultIndicies;
        }
    }
}
