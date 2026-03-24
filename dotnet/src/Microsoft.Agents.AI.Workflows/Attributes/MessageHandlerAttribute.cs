// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Marks a method as a message handler for source-generated route configuration.
/// The method signature determines the input type and optional output type.
/// </summary>
/// <remarks>
/// <para>
/// Methods marked with this attribute must have a signature matching one of the following patterns:
/// <list type="bullet">
/// <item><c>void Handler(TMessage, IWorkflowContext)</c></item>
/// <item><c>void Handler(TMessage, IWorkflowContext, CancellationToken)</c></item>
/// <item><c>ValueTask Handler(TMessage, IWorkflowContext)</c></item>
/// <item><c>ValueTask Handler(TMessage, IWorkflowContext, CancellationToken)</c></item>
/// <item><c>TResult Handler(TMessage, IWorkflowContext)</c></item>
/// <item><c>TResult Handler(TMessage, IWorkflowContext, CancellationToken)</c></item>
/// <item><c>ValueTask&lt;TResult&gt; Handler(TMessage, IWorkflowContext)</c></item>
/// <item><c>ValueTask&lt;TResult&gt; Handler(TMessage, IWorkflowContext, CancellationToken)</c></item>
/// </list>
/// </para>
/// <para>
/// The containing class must be <c>partial</c> and derive from <see cref="Executor"/>.
/// </para>
/// </remarks>
/// <example>
/// <code>
/// public partial class MyExecutor : Executor
/// {
///     [MessageHandler]
///     private async ValueTask&lt;MyResponse&gt; HandleQueryAsync(
///         MyQuery query, IWorkflowContext ctx, CancellationToken ct)
///     {
///         return new MyResponse();
///     }
///
///     [MessageHandler(Yield = [typeof(StreamChunk)], Send = [typeof(InternalMessage)])]
///     private void HandleStream(StreamRequest req, IWorkflowContext ctx)
///     {
///         // Handler with explicit yield and send types
///     }
/// }
/// </code>
/// </example>
[AttributeUsage(AttributeTargets.Method, AllowMultiple = false, Inherited = false)]
public sealed class MessageHandlerAttribute : Attribute
{
    /// <summary>
    /// Gets or sets the types that this handler may yield as workflow outputs.
    /// </summary>
    /// <remarks>
    /// If not specified, the return type (if any) is used as the default yield type.
    /// Use this property to explicitly declare additional output types or to override
    /// the default inference from the return type.
    /// </remarks>
    public Type[]? Yield { get; set; }

    /// <summary>
    /// Gets or sets the types that this handler may send as messages to other executors.
    /// </summary>
    /// <remarks>
    /// Use this property to declare the message types that this handler may send
    /// via <see cref="IWorkflowContext.SendMessageAsync"/> during its execution.
    /// This information is used for protocol validation and documentation.
    /// </remarks>
    public Type[]? Send { get; set; }
}
