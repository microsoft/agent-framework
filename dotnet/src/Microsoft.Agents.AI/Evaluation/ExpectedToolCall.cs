// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;

namespace Microsoft.Agents.AI;

/// <summary>
/// A tool call that an agent is expected to make.
/// </summary>
/// <remarks>
/// Used with <c>EvaluateAsync</c> to assert that the agent called the correct tools.
/// The evaluator decides matching semantics (order, extras, argument checking);
/// this type is pure data.
/// </remarks>
/// <param name="Name">The tool/function name (e.g. <c>"get_weather"</c>).</param>
/// <param name="Arguments">
/// Expected arguments. <c>null</c> means "don't check arguments".
/// When provided, evaluators typically do subset matching (all expected keys must be present).
/// </param>
public record ExpectedToolCall(string Name, IReadOnlyDictionary<string, object>? Arguments = null);
