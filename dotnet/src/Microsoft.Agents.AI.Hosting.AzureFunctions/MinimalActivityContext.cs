// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows;

namespace Microsoft.Agents.AI.Hosting.AzureFunctions;

/// <summary>
/// A minimal implementation of <see cref="IWorkflowContext"/> for use in Azure Functions activities.
/// This provides basic context support for simple executors that don't require full workflow infrastructure.
/// </summary>
internal sealed class MinimalActivityContext : IWorkflowContext
{
    public MinimalActivityContext(string executorId)
    {
        // executorId is provided but not stored since this minimal context doesn't use it
        _ = executorId;
    }

    /// <inheritdoc/>
    public ValueTask AddEventAsync(WorkflowEvent workflowEvent, CancellationToken cancellationToken = default)
    {
        // In activity context, events are not propagated to the workflow
        // They would need to be returned as part of the activity result
        return default;
    }

    /// <inheritdoc/>
    public ValueTask SendMessageAsync(object message, string? targetId = null, CancellationToken cancellationToken = default)
    {
        // In activity context, messages cannot be routed to other executors
        // The orchestration handles message routing between executors
        return default;
    }

    /// <inheritdoc/>
    public ValueTask YieldOutputAsync(object output, CancellationToken cancellationToken = default)
    {
        // In activity context, outputs are not yielded to the workflow
        // They would need to be returned as part of the activity result
        return default;
    }

    /// <inheritdoc/>
    public ValueTask RequestHaltAsync()
    {
        // Halt requests are not supported in activity context
        return default;
    }

    /// <inheritdoc/>
    public ValueTask<T?> ReadStateAsync<T>(string key, string? scopeName = null, CancellationToken cancellationToken = default)
    {
        // No state available in activity context
        return new ValueTask<T?>(default(T));
    }

    /// <inheritdoc/>
    public ValueTask<T> ReadOrInitStateAsync<T>(string key, Func<T> initialStateFactory, string? scopeName = null, CancellationToken cancellationToken = default)
    {
        // Initialize with factory value since no state is available
        return new ValueTask<T>(initialStateFactory());
    }

    /// <inheritdoc/>
    public ValueTask<HashSet<string>> ReadStateKeysAsync(string? scopeName = null, CancellationToken cancellationToken = default)
    {
        // No state keys in activity context
        return new ValueTask<HashSet<string>>([]);
    }

    /// <inheritdoc/>
    public ValueTask QueueStateUpdateAsync<T>(string key, T? value, string? scopeName = null, CancellationToken cancellationToken = default)
    {
        // State updates are not persisted in activity context
        return default;
    }

    /// <inheritdoc/>
    public ValueTask QueueClearScopeAsync(string? scopeName = null, CancellationToken cancellationToken = default)
    {
        // No state to clear in activity context
        return default;
    }

    /// <inheritdoc/>
    public IReadOnlyDictionary<string, string>? TraceContext => null;

    /// <inheritdoc/>
    public bool ConcurrentRunsEnabled => false;
}
