// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;

namespace Microsoft.Agents.Workflows.Reflection;

/// <summary>
/// A component that processes messages in a <see cref="Workflow"/>.
/// </summary>
/// <typeparam name="TExecutor">The actual type of the <see cref="ReflectingExecutor{TExecutor}"/>.
/// This is used to reflectively discover handlers for messages without violating ILTrim requirements.
/// </typeparam>
public class ReflectingExecutor<
    [DynamicallyAccessedMembers(
        ReflectionDemands.RuntimeInterfaceDiscoveryAndInvocation)
    ] TExecutor
    > : Executor where TExecutor : ReflectingExecutor<TExecutor>
{
    /// <inheritdoc cref="Executor.Executor(string?)"/>
    protected ReflectingExecutor(string? id = null) : base(id)
    { }

    /// <inheritdoc />
    protected override RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder)
    {
        return routeBuilder.ReflectHandlers<TExecutor>(this);
    }
}
