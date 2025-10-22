// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Represents the workflow binding details for a shared executor instance, including configuration options
/// for event emission.
/// </summary>
/// <param name="ExecutorInstance">The executor instance to bind. Cannot be null.</param>
public record ExecutorInstanceBinding(Executor ExecutorInstance)
    : ExecutorBinding(Throw.IfNull(ExecutorInstance).Id,
                           (_) => new(ExecutorInstance),
                           ExecutorInstance.GetType(),
                           ExecutorInstance)
{
    /// <inheritdoc/>
    public override bool SupportsConcurrentSharedExecution => this.ExecutorInstance.IsCrossRunShareable;

    /// <inheritdoc/>
    public override bool SupportsResetting => this.ExecutorInstance is IResettableExecutor;

    /// <inheritdoc/>
    public override bool IsSharedInstance => true;

    /// <inheritdoc/>
    protected override async ValueTask<bool> ResetCoreAsync()
    {
        if (this.ExecutorInstance is IResettableExecutor resettable)
        {
            await resettable.ResetAsync().ConfigureAwait(false);
            return true;
        }

        return false;
    }
}
