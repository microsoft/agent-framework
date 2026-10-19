// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// A manager that manages the flow of a group chat.
/// </summary>
public abstract class GroupChatManager
{
    // The state key under which GroupChatManager persists its own (non-subclass) state on the
    // raw IWorkflowContext supplied by the hosting GroupChatHost executor.
    internal const string BaseStateKey = "GroupChatManager";

    // Prefix automatically applied to every key a subclass writes through the wrapped context
    // supplied to OnCheckpointingAsync / OnCheckpointRestoredAsync. Keeps subclass-defined
    // state in its own namespace so it cannot collide with the host's state keys nor with
    // BaseStateKey itself.
    internal const string SubclassStateKeyPrefix = "GroupChatManager_";

    /// <summary>
    /// Initializes a new instance of the <see cref="GroupChatManager"/> class.
    /// </summary>
    protected GroupChatManager() { }

    /// <summary>
    /// Gets the number of iterations in the group chat so far.
    /// </summary>
    public int IterationCount { get; internal set; }

    /// <summary>
    /// Gets or sets the maximum number of iterations allowed.
    /// </summary>
    /// <remarks>
    /// Each iteration involves a single interaction with a participating agent.
    /// The default is 40.
    /// </remarks>
    public int MaximumIterationCount
    {
        get;
        set => field = Throw.IfLessThan(value, 1);
    } = 40;

    /// <summary>
    /// Selects the next agent to participate in the group chat based on the provided chat history and team.
    /// </summary>
    /// <param name="history">The chat history to consider.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.
    /// The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>The next <see cref="AIAgent"/> to speak. This agent must be part of the chat.</returns>
    protected internal abstract ValueTask<AIAgent> SelectNextAgentAsync(
        IReadOnlyList<ChatMessage> history,
        CancellationToken cancellationToken = default);

    /// <summary>
    /// Filters the messages broadcast to participants for the current turn.
    /// </summary>
    /// <remarks>
    /// Under the broadcast model, each participant maintains its own per-agent session (history)
    /// through its <see cref="Specialized.AIAgentHostExecutor"/>. The host distributes new messages
    /// (initial user input on the first turn, the most recent speaker's response on subsequent turns)
    /// to every participant — except the speaker that produced them — so every participant's session
    /// stays synchronized. This method lets the manager shape that broadcast payload (for example,
    /// to omit certain messages or to inject orchestrator-visible annotations). The full canonical
    /// conversation is still available to <see cref="SelectNextAgentAsync"/> and
    /// <see cref="ShouldTerminateAsync"/>.
    /// </remarks>
    /// <param name="history">The new messages about to be broadcast to participants this turn.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.
    /// The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>The filtered message list to broadcast.</returns>
    protected internal virtual ValueTask<IEnumerable<ChatMessage>> UpdateHistoryAsync(
        IReadOnlyList<ChatMessage> history,
        CancellationToken cancellationToken = default) =>
        new(history);

    /// <summary>
    /// Determines whether the group chat should be terminated based on the provided chat history and iteration count.
    /// </summary>
    /// <param name="history">The chat history to consider.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.
    /// The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="bool"/> indicating whether the chat should be terminated.</returns>
    protected internal virtual ValueTask<bool> ShouldTerminateAsync(
        IReadOnlyList<ChatMessage> history,
        CancellationToken cancellationToken = default) =>
        new(this.MaximumIterationCount is int max && this.IterationCount >= max);

    /// <summary>
    /// Resets the state of the manager for a new group chat session.
    /// </summary>
    protected internal virtual void Reset()
    {
        this.IterationCount = 0;
    }

    /// <summary>
    /// Invoked when the hosting group chat workflow is checkpointing, giving subclasses a chance to
    /// persist any additional state they maintain (e.g., a round-robin cursor or an LLM session).
    /// </summary>
    /// <remarks>
    /// <para>
    /// The default implementation is a no-op. Base-class state (currently
    /// <see cref="IterationCount"/>) is persisted automatically by the hosting
    /// <see cref="Specialized.GroupChatHost"/> before this method is invoked; subclasses do not
    /// need to call <c>base.OnCheckpointingAsync</c>.
    /// </para>
    /// <para>
    /// The supplied <paramref name="context"/> is a wrapper that transparently prefixes every
    /// state key with <c>"GroupChatManager_"</c>, isolating subclass state from the host's own
    /// state keys (and from the reserved base-state key). Implementations therefore may use any
    /// human-readable key (e.g., <c>"next_index"</c>) without worrying about collisions.
    /// </para>
    /// </remarks>
    /// <param name="context">A wrapped workflow context that scopes state keys to the
    /// <see cref="GroupChatManager"/> subclass namespace.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.
    /// The default is <see cref="CancellationToken.None"/>.</param>
    protected virtual ValueTask OnCheckpointingAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
        => default;

    /// <summary>
    /// Invoked when the hosting group chat workflow is being restored from a checkpoint, giving
    /// subclasses a chance to hydrate any additional state they persisted in
    /// <see cref="OnCheckpointingAsync"/>.
    /// </summary>
    /// <remarks>
    /// The default implementation is a no-op. Base-class state (currently
    /// <see cref="IterationCount"/>) is restored automatically by the hosting
    /// <see cref="Specialized.GroupChatHost"/> before this method is invoked; subclasses do not
    /// need to call <c>base.OnCheckpointRestoredAsync</c>. The supplied <paramref name="context"/>
    /// uses the same key-prefixing wrapper as <see cref="OnCheckpointingAsync"/>.
    /// </remarks>
    /// <param name="context">A wrapped workflow context that scopes state keys to the
    /// <see cref="GroupChatManager"/> subclass namespace.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.
    /// The default is <see cref="CancellationToken.None"/>.</param>
    protected virtual ValueTask OnCheckpointRestoredAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
        => default;

    // Root checkpoint entry point invoked by the hosting GroupChatHost. Persists the manager's
    // own base state under the reserved BaseStateKey on the raw context, then delegates to the
    // subclass-facing OnCheckpointingAsync hook with a wrapped context that prefixes every key
    // with SubclassStateKeyPrefix.
    internal async ValueTask CheckpointAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        await context.QueueStateUpdateAsync(BaseStateKey, new GroupChatManagerState(this.IterationCount), cancellationToken: cancellationToken).ConfigureAwait(false);
        await this.OnCheckpointingAsync(new PrefixingWorkflowContext(context, SubclassStateKeyPrefix), cancellationToken).ConfigureAwait(false);
    }

    // Root restore entry point invoked by the hosting GroupChatHost. Symmetric to CheckpointAsync.
    internal async ValueTask RestoreCheckpointAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        GroupChatManagerState? state = await context.ReadStateAsync<GroupChatManagerState>(BaseStateKey, cancellationToken: cancellationToken).ConfigureAwait(false);
        this.IterationCount = state?.IterationCount ?? 0;
        await this.OnCheckpointRestoredAsync(new PrefixingWorkflowContext(context, SubclassStateKeyPrefix), cancellationToken).ConfigureAwait(false);
    }
}

internal sealed record GroupChatManagerState(int IterationCount);

// IWorkflowContext decorator that prepends a fixed prefix to every state key passed through it.
// All non-state members (events, message sending, output yielding, halt requests, trace context,
// and runtime characteristics) delegate directly to the wrapped context.
internal sealed class PrefixingWorkflowContext(IWorkflowContext inner, string prefix) : IWorkflowContext
{
    private readonly IWorkflowContext _inner = Throw.IfNull(inner);
    private readonly string _prefix = Throw.IfNullOrEmpty(prefix);

    public IReadOnlyDictionary<string, string>? TraceContext => this._inner.TraceContext;

    public bool ConcurrentRunsEnabled => this._inner.ConcurrentRunsEnabled;

    public ValueTask AddEventAsync(WorkflowEvent workflowEvent, CancellationToken cancellationToken = default)
        => this._inner.AddEventAsync(workflowEvent, cancellationToken);

    public ValueTask SendMessageAsync(object message, string? targetId, CancellationToken cancellationToken = default)
        => this._inner.SendMessageAsync(message, targetId, cancellationToken);

    public ValueTask YieldOutputAsync(object output, CancellationToken cancellationToken = default)
        => this._inner.YieldOutputAsync(output, cancellationToken);

    public ValueTask RequestHaltAsync() => this._inner.RequestHaltAsync();

    public ValueTask<T?> ReadStateAsync<T>(string key, string? scopeName = null, CancellationToken cancellationToken = default)
        => this._inner.ReadStateAsync<T>(this.Wrap(key), scopeName, cancellationToken);

    public ValueTask<T> ReadOrInitStateAsync<T>(string key, Func<T> initialStateFactory, string? scopeName = null, CancellationToken cancellationToken = default)
        => this._inner.ReadOrInitStateAsync(this.Wrap(key), initialStateFactory, scopeName, cancellationToken);

    public async ValueTask<HashSet<string>> ReadStateKeysAsync(string? scopeName = null, CancellationToken cancellationToken = default)
    {
        HashSet<string> rawKeys = await this._inner.ReadStateKeysAsync(scopeName, cancellationToken).ConfigureAwait(false);
        return [.. rawKeys.Where(k => k.StartsWith(this._prefix, StringComparison.Ordinal))
                          .Select(k => k.Substring(this._prefix.Length))];
    }

    public ValueTask QueueStateUpdateAsync<T>(string key, T? value, string? scopeName = null, CancellationToken cancellationToken = default)
        => this._inner.QueueStateUpdateAsync(this.Wrap(key), value, scopeName, cancellationToken);

    public async ValueTask QueueClearScopeAsync(string? scopeName = null, CancellationToken cancellationToken = default)
    {
        // Clearing the entire underlying scope would also remove keys owned by the host and other
        // subsystems sharing the executor's default scope. Restrict the clear to keys carrying
        // this wrapper's prefix.
        HashSet<string> rawKeys = await this._inner.ReadStateKeysAsync(scopeName, cancellationToken).ConfigureAwait(false);
        foreach (string rawKey in rawKeys)
        {
            if (rawKey.StartsWith(this._prefix, StringComparison.Ordinal))
            {
                await this._inner.QueueStateUpdateAsync<object>(rawKey, null, scopeName, cancellationToken).ConfigureAwait(false);
            }
        }
    }

    private string Wrap(string key) => this._prefix + Throw.IfNullOrEmpty(key);
}
