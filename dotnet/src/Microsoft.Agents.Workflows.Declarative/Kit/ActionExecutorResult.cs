// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.Workflows.Declarative.Kit;

/// <summary>
/// Represents the result of an action executor.
/// </summary>
/// <param name="ExecutorId"></param>
/// <param name="Result"></param>
public sealed record class ActionExecutorResult(string ExecutorId, object? Result = null);
