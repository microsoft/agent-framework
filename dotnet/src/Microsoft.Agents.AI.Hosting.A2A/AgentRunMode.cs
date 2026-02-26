// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI.Hosting.A2A;

/// <summary>
/// Specifies how the A2A hosting layer determines whether to run <see cref="AIAgent"/> in background or not.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AIResponseContinuations)]
public sealed class AgentRunMode : IEquatable<AgentRunMode>
{
    private const string MessageValue = "message";
    private const string TaskValue = "task";
    private const string DynamicValue = "dynamic";

    private readonly string _value;
    private readonly Func<A2ARunDecisionContext, CancellationToken, ValueTask<bool>>? _runInBackground;

    private AgentRunMode(string value, Func<A2ARunDecisionContext, CancellationToken, ValueTask<bool>>? runInBackground = null)
    {
        this._value = value;
        this._runInBackground = runInBackground;
    }

    /// <summary>
    /// Dissallows the background responses from the agent. Is equivalent to configuring <see cref="AgentRunOptions.AllowBackgroundResponses"/> as <c>false</c>.
    /// In the A2A protocol terminology will make responses be returned as <c>AgentMessage</c>.
    /// </summary>
    public static AgentRunMode DisallowBackground => new(MessageValue);

    /// <summary>
    /// Allows the background responses from the agent. Is equivalent to configuring <see cref="AgentRunOptions.AllowBackgroundResponses"/> as <c>true</c>.
    /// In the A2A protocol terminology will make responses be returned as <c>AgentTask</c> if the agent supports background responses, and as <c>AgentMessage</c> otherwise.
    /// </summary>
    public static AgentRunMode AllowBackgroundIfSupported => new(TaskValue);

    /// <summary>
    /// The agent run mode is decided by the supplied <paramref name="runInBackground"/> delegate.
    /// The delegate receives an <see cref="A2ARunDecisionContext"/> with the incoming
    /// message and returns a boolean specifying whether to run the agent in background mode.
    /// <see langword="true"/> indicates that the agent should run in background mode and return an
    /// <c>AgentTask</c> if the agent supports background mode; otherwise, it returns an <c>AgentMessage</c>
    /// if the mode is not supported. <see langword="false"/> indicates that the agent should run in
    /// non-background mode and return an <c>AgentMessage</c>.
    /// </summary>
    /// <param name="runInBackground">
    /// An async delegate that decides whether the response should be wrapped in an <c>AgentTask</c>.
    /// </param>
    public static AgentRunMode AllowBackgroundWhen(Func<A2ARunDecisionContext, CancellationToken, ValueTask<bool>> runInBackground)
    {
        ArgumentNullException.ThrowIfNull(runInBackground);
        return new(DynamicValue, runInBackground);
    }

    /// <summary>
    /// Determines whether the agent response should be returned as an <c>AgentTask</c>.
    /// </summary>
    internal ValueTask<bool> ShouldRunInBackgroundAsync(A2ARunDecisionContext context, CancellationToken cancellationToken)
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
        if (this._runInBackground is not null)
        {
            return this._runInBackground(context, cancellationToken);
        }

        // No delegate provided — fall back to "message" behavior.
        return ValueTask.FromResult(true);
    }

    /// <inheritdoc/>
    public bool Equals(AgentRunMode? other) =>
        other is not null && string.Equals(this._value, other._value, StringComparison.OrdinalIgnoreCase);

    /// <inheritdoc/>
    public override bool Equals(object? obj) => this.Equals(obj as AgentRunMode);

    /// <inheritdoc/>
    public override int GetHashCode() => StringComparer.OrdinalIgnoreCase.GetHashCode(this._value);

    /// <inheritdoc/>
    public override string ToString() => this._value;

    /// <summary>Determines whether two <see cref="AgentRunMode"/> instances are equal.</summary>
    public static bool operator ==(AgentRunMode? left, AgentRunMode? right) =>
        left?.Equals(right) ?? right is null;

    /// <summary>Determines whether two <see cref="AgentRunMode"/> instances are not equal.</summary>
    public static bool operator !=(AgentRunMode? left, AgentRunMode? right) =>
        !(left == right);
}
