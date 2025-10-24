// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Initializes a new instance of the ExecutorRegistrationEx class using the specified executor.
/// </summary>
/// <param name="ExecutorInstance">The executor instance to register. Cannot be null.</param>
public record ExecutorInstanceRegistration(Executor ExecutorInstance)
    : ExecutorRegistration(Throw.IfNull(ExecutorInstance).Id,
                           (_) => new(ExecutorInstance),
                           ExecutorInstance.GetType(),
                           ExecutorInstance)
{
    /// <inheritdoc/>
    public override bool SupportsConcurrentSharedExecution => this.ExecutorInstance.IsCrossRunShareable;

    /// <inheritdoc/>
    public override bool SupportsResetting => this.ExecutorInstance is IResettableExecutor;

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
