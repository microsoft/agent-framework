// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using A2A;

namespace Microsoft.Agents.AI.Hosting.A2A;

/// <summary>
/// A delegating <see cref="ITaskStore"/> that scopes task keys by an isolation key
/// provided by an <see cref="AgentIsolationKeyProvider"/>, ensuring that tasks are isolated
/// per logical partition (e.g., user, tenant, or composite key).
/// </summary>
/// <remarks>
/// <para>
/// This class mirrors the isolation pattern of <see cref="IsolationKeyScopedAgentSessionStore"/>
/// but applies it to the A2A task store, preventing cross-tenant task access in multi-tenant deployments.
/// </para>
/// <para>
/// Both the store key and the persisted <see cref="AgentTask.ContextId"/> are scoped with the isolation
/// key. Scoping the persisted context is what allows list queries to be constrained to the calling
/// tenant, because list results are matched against the task body rather than the store key. Scoped
/// values are stripped again before being returned, so callers only ever observe bare identifiers.
/// </para>
/// </remarks>
public sealed class IsolationKeyScopedTaskStore : ITaskStore
{
    private readonly ITaskStore _innerStore;
    private readonly AgentIsolationKeyProvider? _keyProvider;
    private readonly bool _strict;

    /// <summary>
    /// Initializes a new instance of the <see cref="IsolationKeyScopedTaskStore"/> class.
    /// </summary>
    /// <param name="innerStore">The underlying <see cref="ITaskStore"/> to delegate to.</param>
    /// <param name="keyProvider">
    /// The <see cref="AgentIsolationKeyProvider"/> used to retrieve the isolation key for the current context.
    /// </param>
    /// <param name="strict">
    /// When <see langword="true"/>, an <see cref="InvalidOperationException"/> is thrown if the isolation key
    /// cannot be determined. When <see langword="false"/>, the task ID is passed through unmodified.
    /// </param>
    /// <exception cref="ArgumentNullException"><paramref name="innerStore"/> is <see langword="null"/>.</exception>
    public IsolationKeyScopedTaskStore(
        ITaskStore innerStore,
        AgentIsolationKeyProvider? keyProvider,
        bool strict)
    {
        ArgumentNullException.ThrowIfNull(innerStore);

        this._innerStore = innerStore;
        this._keyProvider = keyProvider;
        this._strict = strict;
    }

    /// <inheritdoc />
    public async Task<AgentTask?> GetTaskAsync(string taskId, CancellationToken cancellationToken = default)
    {
        string? key = await this.GetIsolationKeyAsync(cancellationToken).ConfigureAwait(false);

        var task = await this._innerStore.GetTaskAsync(ScopeId(taskId, key), cancellationToken).ConfigureAwait(false);

        return task is null ? null : UnscopeTask(task, key);
    }

    /// <inheritdoc />
    public async Task SaveTaskAsync(string taskId, AgentTask task, CancellationToken cancellationToken = default)
    {
        string? key = await this.GetIsolationKeyAsync(cancellationToken).ConfigureAwait(false);

        await this._innerStore.SaveTaskAsync(ScopeId(taskId, key), ScopeTask(task, key), cancellationToken).ConfigureAwait(false);
    }

    /// <inheritdoc />
    public async Task DeleteTaskAsync(string taskId, CancellationToken cancellationToken = default)
    {
        string? key = await this.GetIsolationKeyAsync(cancellationToken).ConfigureAwait(false);

        await this._innerStore.DeleteTaskAsync(ScopeId(taskId, key), cancellationToken).ConfigureAwait(false);
    }

    /// <inheritdoc />
    /// <remarks>
    /// <see cref="ListTasksResponse.TotalSize"/> is reported by the inner store. When no
    /// <see cref="ListTasksRequest.ContextId"/> filter is supplied it therefore counts tasks across all
    /// isolation keys, because a wrapper cannot narrow the count without enumerating the whole store.
    /// The returned tasks themselves are always constrained to the current isolation key.
    /// </remarks>
    public async Task<ListTasksResponse> ListTasksAsync(ListTasksRequest request, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(request);

        string? key = await this.GetIsolationKeyAsync(cancellationToken).ConfigureAwait(false);

        if (key is not null && !string.IsNullOrEmpty(request.ContextId))
        {
            // Clone the request to avoid mutating the caller's object.
            request = CloneRequestWithContextId(request, ScopeId(request.ContextId!, key));
        }

        var response = await this._innerStore.ListTasksAsync(request, cancellationToken).ConfigureAwait(false);

        if (key is null)
        {
            return response;
        }

        // Tasks are persisted with a scoped ContextId, so any entry that does not carry the current
        // isolation key belongs to another tenant and must not be returned.
        var scopedTasks = new List<AgentTask>(response.Tasks.Count);
        foreach (var task in response.Tasks)
        {
            if (IsInScope(task, key))
            {
                scopedTasks.Add(UnscopeTask(task, key));
            }
        }

        response.Tasks = scopedTasks;
        response.PageSize = scopedTasks.Count;

        return response;
    }

    /// <summary>
    /// Asynchronously retrieves the isolation key from the provider and validates it if in strict mode.
    /// </summary>
    private async ValueTask<string?> GetIsolationKeyAsync(CancellationToken cancellationToken)
    {
        string? key = this._keyProvider != null
                    ? await this._keyProvider.GetIsolationKeyAsync(cancellationToken).ConfigureAwait(false)
                    : null;

        if (this._strict && key == null)
        {
            throw new InvalidOperationException("Agent isolation key is required but was not provided by the configured AgentIsolationKeyProvider.");
        }

        return key;
    }

    /// <summary>
    /// Escapes special characters in the isolation key to ensure unambiguous scoped identifiers.
    /// </summary>
    private static string EscapeIsolationKey(string key) => key.Replace("\\", "\\\\").Replace(":", "\\:");

    /// <summary>
    /// Prefixes a bare identifier with the escaped isolation key, or returns it unchanged when no key applies.
    /// </summary>
    private static string ScopeId(string id, string? key)
        => key is null ? id : $"{EscapeIsolationKey(key)}::{id}";

    /// <summary>
    /// Strips the isolation key prefix from a scoped identifier, or returns it unchanged when the prefix is absent.
    /// </summary>
    private static string UnscopeId(string scopedId, string? key)
    {
        if (key is null)
        {
            return scopedId;
        }

        string prefix = $"{EscapeIsolationKey(key)}::";

        return scopedId.StartsWith(prefix, StringComparison.Ordinal)
            ? scopedId.Substring(prefix.Length)
            : scopedId;
    }

    /// <summary>
    /// Determines whether a persisted task carries the supplied isolation key.
    /// </summary>
    private static bool IsInScope(AgentTask task, string key)
        => task.ContextId?.StartsWith($"{EscapeIsolationKey(key)}::", StringComparison.Ordinal) == true;

    /// <summary>
    /// Creates a copy of the task whose <see cref="AgentTask.ContextId"/> is scoped by the isolation key.
    /// </summary>
    /// <remarks>
    /// The task instance is copied rather than mutated because the A2A server reuses it for live event
    /// notification after persisting; mutating it would surface the scoped context on the wire.
    /// </remarks>
    private static AgentTask ScopeTask(AgentTask task, string? key)
        => key is null ? task : CloneTaskWithContextId(task, ScopeId(task.ContextId, key));

    /// <summary>
    /// Creates a copy of the task whose <see cref="AgentTask.ContextId"/> has the isolation key removed.
    /// </summary>
    private static AgentTask UnscopeTask(AgentTask task, string? key)
        => key is null ? task : CloneTaskWithContextId(task, UnscopeId(task.ContextId, key));

    private static AgentTask CloneTaskWithContextId(AgentTask task, string contextId)
        => new()
        {
            Id = task.Id,
            ContextId = contextId,
            Status = task.Status,
            History = task.History,
            Artifacts = task.Artifacts,
            Metadata = task.Metadata,
        };

    private static ListTasksRequest CloneRequestWithContextId(ListTasksRequest request, string contextId)
        => new()
        {
            ContextId = contextId,
            Tenant = request.Tenant,
            Status = request.Status,
            PageSize = request.PageSize,
            PageToken = request.PageToken,
            HistoryLength = request.HistoryLength,
            StatusTimestampAfter = request.StatusTimestampAfter,
            IncludeArtifacts = request.IncludeArtifacts,
        };
}
