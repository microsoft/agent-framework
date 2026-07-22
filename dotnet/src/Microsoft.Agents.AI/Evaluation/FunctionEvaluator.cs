// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.AI;

/// <summary>
/// Factory for creating <see cref="EvalCheck"/> delegates from typed lambda functions.
/// </summary>
public static class FunctionEvaluator
{
    /// <summary>
    /// Creates a check from a function that takes the response text and returns a bool.
    /// </summary>
    /// <param name="name">Check name for reporting.</param>
    /// <param name="check">Function that returns true if the response passes.</param>
    public static EvalCheck Create(string name, Func<string, bool> check)
    {
        return (EvalItem item) =>
        {
            var passed = check(item.Response);
            return new EvalCheckResult(passed, passed ? "Passed" : "Failed", name);
        };
    }

    /// <summary>
    /// Creates a check from a function that takes response and expected text.
    /// </summary>
    /// <param name="name">Check name for reporting.</param>
    /// <param name="check">Function that returns true if the response passes.</param>
    public static EvalCheck Create(string name, Func<string, string?, bool> check)
    {
        return (EvalItem item) =>
        {
            var passed = check(item.Response, item.ExpectedOutput);
            return new EvalCheckResult(passed, passed ? "Passed" : "Failed", name);
        };
    }

    /// <summary>
    /// Creates a check from a function that takes the full <see cref="EvalItem"/>.
    /// </summary>
    /// <param name="name">Check name for reporting.</param>
    /// <param name="check">Function that returns true if the item passes.</param>
    public static EvalCheck Create(string name, Func<EvalItem, bool> check)
    {
        return (EvalItem item) =>
        {
            var passed = check(item);
            return new EvalCheckResult(passed, passed ? "Passed" : "Failed", name);
        };
    }

    /// <summary>
    /// Creates a check from a function that takes the full <see cref="EvalItem"/>
    /// and returns a <see cref="EvalCheckResult"/>.
    /// </summary>
    /// <param name="name">Check name (used as fallback if the result has no name).</param>
    /// <param name="check">Function that returns a full check result.</param>
    public static EvalCheck Create(string name, Func<EvalItem, EvalCheckResult> check)
    {
        return (EvalItem item) =>
        {
            var result = check(item);
            return result with { CheckName = result.CheckName ?? name };
        };
    }
}
