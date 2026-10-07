// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Extensions.AI;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides extension methods for the <see cref="FunctionInvocationContext"/> instances that are passed to the
/// function invocation callbacks registered with <see cref="FunctionInvocationDelegatingAgentBuilderExtensions"/>.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public static class FunctionInvocationContextExtensions
{
    /// <summary>
    /// Wraps the provided <see cref="AIFunction"/> with the function invocation callbacks that have not run yet
    /// for the invocation represented by <paramref name="context"/>.
    /// </summary>
    /// <param name="context">The context passed to the function invocation callback that is currently running.</param>
    /// <param name="function">The function to wrap.</param>
    /// <returns>
    /// The wrapped function, or <paramref name="function"/> itself when no other callbacks are pending for this invocation.
    /// </returns>
    /// <exception cref="ArgumentNullException"><paramref name="context"/> or <paramref name="function"/> is <see langword="null"/>.</exception>
    /// <exception cref="InvalidOperationException">
    /// No function invocation callback is running for <paramref name="context"/>, or the running callback already
    /// called its continuation.
    /// </exception>
    /// <remarks>
    /// <para>
    /// A callback that assigns a different function to <see cref="FunctionInvocationContext.Function"/> replaces the
    /// function that the continuation invokes. The replacement is invoked directly, so the callbacks registered after
    /// the one performing the replacement do not observe that invocation. Use this method to wrap the replacement so
    /// that those callbacks run for it as well.
    /// </para>
    /// <para>
    /// This method must be called by a function invocation callback that is running for <paramref name="context"/>,
    /// and before that callback calls its continuation. Once the continuation ran, the callbacks it went through
    /// are no longer pending, so the callbacks to wrap can no longer be determined.
    /// </para>
    /// </remarks>
    public static AIFunction WrapWithPendingMiddleware(this FunctionInvocationContext context, AIFunction function)
    {
        _ = Throw.IfNull(context);
        _ = Throw.IfNull(function);

        return FunctionInvocationDelegatingAgent.WrapWithPendingMiddleware(context, function);
    }
}
