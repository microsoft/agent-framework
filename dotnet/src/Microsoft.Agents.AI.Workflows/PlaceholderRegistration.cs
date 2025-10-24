// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Represents a registration entry for an executor placeholder, identified by a unique ID.
/// </summary>
/// <param name="Id">The unique identifier for the placeholder registration.</param>
public record PlaceholderRegistration(string Id)
    : ExecutorRegistration(Id,
                           null,
                           typeof(Executor),
                           Id)
{
    /// <inheritdoc/>
    public override bool SupportsConcurrentSharedExecution => false;

    /// <inheritdoc/>
    public override bool SupportsResetting => false;
}
