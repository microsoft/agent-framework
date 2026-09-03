// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI.Hosting.A2A;

/// <summary>
/// Specifies which A2A protocol artifact the hosting layer returns for a run of an <see cref="AIAgent"/>:
/// an <c>AgentMessage</c> or an <c>AgentTask</c>.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AIResponseContinuations)]
public sealed class AgentRunMode : IEquatable<AgentRunMode>
{
    private const string MessageValue = "message";
    private const string TaskValue = "task";
    private const string DynamicValue = "dynamic";

    private readonly string _value;
    private readonly Func<A2ARunDecisionContext, CancellationToken, ValueTask<bool>>? _returnTask;

    private AgentRunMode(string value, Func<A2ARunDecisionContext, CancellationToken, ValueTask<bool>>? returnTask = null)
    {
        this._value = value;
        this._returnTask = returnTask;
    }

    /// <summary>
    /// Returns the agent response as an <c>AgentMessage</c>. The updates produced by the agent are aggregated
    /// into a single message.
    /// </summary>
    public static AgentRunMode ReturnMessage => new(MessageValue);

    /// <summary>
    /// Returns the agent response as an <c>AgentTask</c>, allowing the caller to track its lifecycle and to
    /// receive the result incrementally.
    /// </summary>
    public static AgentRunMode ReturnTask => new(TaskValue);

    /// <summary>
    /// Defers the choice between an <c>AgentMessage</c> and an <c>AgentTask</c> to the supplied
    /// <paramref name="returnTask"/> delegate, which is invoked for each new-message request. The delegate receives
    /// an <see cref="A2ARunDecisionContext"/> describing the incoming request and returns <see langword="true"/> to
    /// return an <c>AgentTask</c>, or <see langword="false"/> to return an <c>AgentMessage</c>. Continuations of an
    /// existing task remain task responses and do not invoke the delegate.
    /// </summary>
    /// <param name="returnTask">
    /// An async delegate that decides whether a new-message response is returned as an <c>AgentTask</c>.
    /// </param>
    public static AgentRunMode ReturnTaskWhen(Func<A2ARunDecisionContext, CancellationToken, ValueTask<bool>> returnTask)
    {
        ArgumentNullException.ThrowIfNull(returnTask);
        return new(DynamicValue, returnTask);
    }

    /// <summary>
    /// Determines whether the agent response should be returned as an <c>AgentTask</c>.
    /// </summary>
    internal ValueTask<bool> ShouldReturnTaskAsync(A2ARunDecisionContext context, CancellationToken cancellationToken)
    {
        if (string.Equals(this._value, MessageValue, StringComparison.OrdinalIgnoreCase))
        {
            return ValueTask.FromResult(false);
        }

        if (string.Equals(this._value, TaskValue, StringComparison.OrdinalIgnoreCase))
        {
            return ValueTask.FromResult(true);
        }

        // Dynamic: delegate to custom callback.
        if (this._returnTask is not null)
        {
            return this._returnTask(context, cancellationToken);
        }

        // No delegate provided — fall back to "message" behavior.
        return ValueTask.FromResult(false);
    }

    /// <inheritdoc/>
    public bool Equals(AgentRunMode? other) =>
        other is not null
        && string.Equals(this._value, other._value, StringComparison.OrdinalIgnoreCase)
        && ReferenceEquals(this._returnTask, other._returnTask);

    /// <inheritdoc/>
    public override bool Equals(object? obj) => this.Equals(obj as AgentRunMode);

    /// <inheritdoc/>
    public override int GetHashCode() => HashCode.Combine(
        StringComparer.OrdinalIgnoreCase.GetHashCode(this._value),
        RuntimeHelpers.GetHashCode(this._returnTask));

    /// <inheritdoc/>
    public override string ToString() => this._value;

    /// <summary>Determines whether two <see cref="AgentRunMode"/> instances are equal.</summary>
    public static bool operator ==(AgentRunMode? left, AgentRunMode? right) =>
        left?.Equals(right) ?? right is null;

    /// <summary>Determines whether two <see cref="AgentRunMode"/> instances are not equal.</summary>
    public static bool operator !=(AgentRunMode? left, AgentRunMode? right) =>
        !(left == right);
}
