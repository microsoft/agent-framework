// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI.Hosting.OpenAI;

/// <summary>
/// Defines how a client-provided function declaration is handled when its name conflicts with a
/// function configured by the hosted agent developer.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public abstract class OpenAIClientFunctionToolNameConflictBehavior
{
    private protected OpenAIClientFunctionToolNameConflictBehavior()
    {
    }

    /// <summary>
    /// Creates a behavior that rejects the request.
    /// </summary>
    /// <returns>The conflict behavior.</returns>
    public static OpenAIClientFunctionToolNameConflictBehavior Reject() => new RejectBehavior();

    /// <summary>
    /// Creates a behavior that keeps the hosted agent function, ignores the client declaration,
    /// and writes a server warning.
    /// </summary>
    /// <returns>The conflict behavior.</returns>
    public static OpenAIClientFunctionToolNameConflictBehavior Ignore() => new IgnoreBehavior();

    /// <summary>
    /// Creates a behavior that uses the client declaration instead of the hosted agent function for
    /// that request.
    /// </summary>
    /// <returns>The conflict behavior.</returns>
    public static OpenAIClientFunctionToolNameConflictBehavior AllowOverride() => new AllowOverrideBehavior();

    internal abstract OpenAIClientFunctionToolNameConflictBehaviorKind Kind { get; }

    private sealed class RejectBehavior : OpenAIClientFunctionToolNameConflictBehavior
    {
        internal override OpenAIClientFunctionToolNameConflictBehaviorKind Kind =>
            OpenAIClientFunctionToolNameConflictBehaviorKind.Reject;
    }

    private sealed class IgnoreBehavior : OpenAIClientFunctionToolNameConflictBehavior
    {
        internal override OpenAIClientFunctionToolNameConflictBehaviorKind Kind =>
            OpenAIClientFunctionToolNameConflictBehaviorKind.Ignore;
    }

    private sealed class AllowOverrideBehavior : OpenAIClientFunctionToolNameConflictBehavior
    {
        internal override OpenAIClientFunctionToolNameConflictBehaviorKind Kind =>
            OpenAIClientFunctionToolNameConflictBehaviorKind.AllowOverride;
    }
}

internal enum OpenAIClientFunctionToolNameConflictBehaviorKind
{
    Reject,
    Ignore,
    AllowOverride,
}
