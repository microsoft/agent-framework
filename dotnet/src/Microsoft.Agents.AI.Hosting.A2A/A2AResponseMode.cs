// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Hosting.A2A;

/// <summary>
/// Specifies how the A2A hosting layer determines whether to return an
/// <c>AgentMessage</c> or an <c>AgentTask</c> from <see cref="AIAgentExtensions"/>.
/// </summary>
public sealed class A2AResponseMode : IEquatable<A2AResponseMode>
{
    private readonly string _value;
    private readonly Func<A2AResponseDecisionContext, ValueTask<bool>>? _decide;

    private A2AResponseMode(string value, Func<A2AResponseDecisionContext, ValueTask<bool>>? decide = null)
    {
        this._value = value;
        this._decide = decide;
    }

    /// <summary>
    /// Always return an <c>AgentMessage</c>. Background responses are not enabled.
    /// Suitable for lightweight, single-shot request/response interactions.
    /// </summary>
    public static A2AResponseMode Message { get; } = new("message");

    /// <summary>
    /// Always return an <c>AgentTask</c>. A task is created and tracked for every
    /// request, even if the agent completes immediately. Background responses are enabled
    /// so the agent can signal long-running operations if supported.
    /// </summary>
    public static A2AResponseMode Task { get; } = new("task");

    /// <summary>
    /// The response type is decided dynamically using the default heuristic: an
    /// <c>AgentTask</c> is returned when the agent produces a continuation token
    /// (indicating a long-running operation); otherwise an <c>AgentMessage</c> is returned.
    /// Background responses are enabled.
    /// </summary>
    public static A2AResponseMode Dynamic() => new("dynamic");

    /// <summary>
    /// The response type is decided by the supplied <paramref name="decideAsTask"/> delegate.
    /// The delegate receives an <see cref="A2AResponseDecisionContext"/> with the incoming
    /// message and the agent response, and returns <see langword="true"/> to return an
    /// <c>AgentTask</c> or <see langword="false"/> to return an <c>AgentMessage</c>.
    /// Background responses are enabled.
    /// </summary>
    /// <param name="decideAsTask">
    /// An async delegate that decides whether the response should be wrapped in an <c>AgentTask</c>.
    /// </param>
    public static A2AResponseMode Dynamic(Func<A2AResponseDecisionContext, ValueTask<bool>> decideAsTask)
    {
        ArgumentNullException.ThrowIfNull(decideAsTask);
        return new("dynamic", decideAsTask);
    }

    /// <summary>
    /// Gets whether background (long-running) responses are enabled for this mode.
    /// </summary>
    internal bool AllowBackgroundResponses =>
        !string.Equals(this._value, "message", StringComparison.OrdinalIgnoreCase);

    /// <summary>
    /// Determines whether the agent response should be returned as an <c>AgentTask</c>.
    /// </summary>
#pragma warning disable MEAI001 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.
    internal ValueTask<bool> ShouldReturnAsTaskAsync(A2AResponseDecisionContext context)
    {
        if (string.Equals(this._value, "message", StringComparison.OrdinalIgnoreCase))
        {
            return ValueTask.FromResult(false);
        }

        if (string.Equals(this._value, "task", StringComparison.OrdinalIgnoreCase))
        {
            return ValueTask.FromResult(true);
        }

        // Dynamic: delegate to custom callback if provided, otherwise use the default
        // heuristic of checking whether the agent returned a continuation token.
        if (this._decide is not null)
        {
            return this._decide(context);
        }

        return ValueTask.FromResult(context.AgentResponse.ContinuationToken is not null);
    }
#pragma warning restore MEAI001

    /// <inheritdoc/>
    public bool Equals(A2AResponseMode? other) =>
        other is not null && string.Equals(this._value, other._value, StringComparison.OrdinalIgnoreCase);

    /// <inheritdoc/>
    public override bool Equals(object? obj) => this.Equals(obj as A2AResponseMode);

    /// <inheritdoc/>
    public override int GetHashCode() => StringComparer.OrdinalIgnoreCase.GetHashCode(this._value);

    /// <inheritdoc/>
    public override string ToString() => this._value;

    /// <summary>Determines whether two <see cref="A2AResponseMode"/> instances are equal.</summary>
    public static bool operator ==(A2AResponseMode? left, A2AResponseMode? right) =>
        left?.Equals(right) ?? right is null;

    /// <summary>Determines whether two <see cref="A2AResponseMode"/> instances are not equal.</summary>
    public static bool operator !=(A2AResponseMode? left, A2AResponseMode? right) =>
        !(left == right);
}
