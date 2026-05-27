// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI;

/// <summary>
/// Delegate for a synchronous evaluation check on a single item.
/// </summary>
/// <param name="item">The evaluation item.</param>
/// <returns>The check result.</returns>
public delegate EvalCheckResult EvalCheck(EvalItem item);
