// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.Workflows.Declarative.Kit;

/// <summary>
/// Base class for an action executor that receives the initial trigger message.
/// </summary>
public abstract class StatefulExecutor : Executor<ActionExecutorResult>
{
    /// <summary>
    /// Initializes a new instance of the <see cref="ActionExecutor"/> class.
    /// </summary>
    /// <param name="id">The executor id</param>
    protected StatefulExecutor(string id)
        : base(id)
    {
    }
}
