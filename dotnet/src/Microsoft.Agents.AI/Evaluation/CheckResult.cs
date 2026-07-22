// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI;

/// <summary>
/// Result of a single check on a single evaluation item.
/// </summary>
/// <param name="Passed">Whether the check passed.</param>
/// <param name="Reason">Human-readable explanation.</param>
/// <param name="CheckName">Name of the check that produced this result.</param>
public sealed record EvalCheckResult(bool Passed, string Reason, string CheckName);
