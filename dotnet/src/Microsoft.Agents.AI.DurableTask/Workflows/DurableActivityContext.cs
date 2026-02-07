// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;
using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using Microsoft.Agents.AI.Workflows;

namespace Microsoft.Agents.AI.DurableTask.Workflows;

/// <summary>
/// A workflow context for durable activity execution.
/// </summary>
/// <remarks>
/// Some of the methods are returning default for this version. Those method will be updated with real implementations in follow up PRs.
/// </remarks>
[DebuggerDisplay("Executor = {_executor.Id}, StateEntries = {_initialState.Count}")]
internal sealed class DurableActivityContext : IWorkflowContext
{
    private readonly Dictionary<string, string> _initialState;
    private readonly Executor _executor;

    /// <summary>
    /// Initializes a new instance of the <see cref="DurableActivityContext"/> class.
    /// </summary>
    /// <param name="initialState">The shared state passed from the orchestration.</param>
    /// <param name="executor">The executor running in this context.</param>
    internal DurableActivityContext(Dictionary<string, string>? initialState, Executor executor)
    {
        this._executor = executor;
        this._initialState = initialState ?? [];
    }

    /// <summary>
    /// Gets the messages sent during activity execution via <see cref="SendMessageAsync"/>.
    /// </summary>
    internal List<SentMessageInfo> SentMessages { get; } = [];

    /// <inheritdoc/>
    public ValueTask AddEventAsync(
        WorkflowEvent workflowEvent,
        CancellationToken cancellationToken = default) => default;

    /// <inheritdoc/>
    [UnconditionalSuppressMessage("AOT", "IL3050", Justification = "Serializing workflow message types registered at startup.")]
    [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Serializing workflow message types registered at startup.")]
    public ValueTask SendMessageAsync(
        object message,
        string? targetId = null,
        CancellationToken cancellationToken = default)
    {
        if (message is not null)
        {
            Type messageType = message.GetType();
            this.SentMessages.Add(new SentMessageInfo
            {
                Message = JsonSerializer.Serialize(message, messageType),
                TypeName = messageType.FullName ?? messageType.Name
            });
        }

        return default;
    }

    /// <inheritdoc/>
    public ValueTask YieldOutputAsync(
        object output,
        CancellationToken cancellationToken = default) => default;

    /// <inheritdoc/>
    public ValueTask RequestHaltAsync() => default;

    /// <inheritdoc/>
    public ValueTask<T?> ReadStateAsync<T>(
        string key,
        string? scopeName = null,
        CancellationToken cancellationToken = default) => default;

    /// <inheritdoc/>
    public ValueTask<T> ReadOrInitStateAsync<T>(
        string key,
        Func<T> initialStateFactory,
        string? scopeName = null,
        CancellationToken cancellationToken = default) => default;

    /// <inheritdoc/>
    public ValueTask<HashSet<string>> ReadStateKeysAsync(
        string? scopeName = null,
        CancellationToken cancellationToken = default) => default;

    /// <inheritdoc/>
    public ValueTask QueueStateUpdateAsync<T>(
        string key,
        T? value,
        string? scopeName = null,
        CancellationToken cancellationToken = default) => default;

    /// <inheritdoc/>
    public ValueTask QueueClearScopeAsync(
        string? scopeName = null,
        CancellationToken cancellationToken = default) => default;

    /// <inheritdoc/>
    public IReadOnlyDictionary<string, string>? TraceContext => null;

    /// <inheritdoc/>
    public bool ConcurrentRunsEnabled => false;
}
