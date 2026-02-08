// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Represents a placeholder entry for an <see cref="ExecutorBinding"/>, identified by a unique ID.
/// </summary>
/// <param name="Id">The unique identifier for the placeholder registration.</param>
public record ExecutorPlaceholder(string Id)
    : ExecutorBinding(Id,
                           null,
                           typeof(Executor),
                           Id)
{
    /// <inheritdoc/>
    public override bool SupportsConcurrentSharedExecution => false;

    /// <inheritdoc/>
    public override bool SupportsResetting => false;

    /// <inheritdoc/>
    public override bool IsSharedInstance => false;
}
