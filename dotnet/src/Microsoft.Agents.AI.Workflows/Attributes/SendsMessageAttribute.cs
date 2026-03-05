// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Declares that an executor may send messages of the specified type.
/// </summary>
/// <remarks>
/// <para>
/// Apply this attribute to an <see cref="Executor"/> class to declare the types of messages
/// it may send via <see cref="IWorkflowContext.SendMessageAsync"/>. This information is used
/// for protocol validation and documentation.
/// </para>
/// <para>
/// This attribute can be applied multiple times to declare multiple message types.
/// It is inherited by derived classes, allowing base executors to declare common message types.
/// </para>
/// </remarks>
/// <example>
/// <code>
/// [SendsMessage(typeof(PollToken))]
/// [SendsMessage(typeof(StatusUpdate))]
/// public partial class MyExecutor : Executor
/// {
///     // ...
/// }
/// </code>
/// </example>
[AttributeUsage(AttributeTargets.Class | AttributeTargets.Method, AllowMultiple = true, Inherited = true)]
public sealed class SendsMessageAttribute : Attribute
{
    /// <summary>
    /// Gets the type of message that the executor may send.
    /// </summary>
    public Type Type { get; }

    /// <summary>
    /// Initializes a new instance of the <see cref="SendsMessageAttribute"/> class.
    /// </summary>
    /// <param name="type">The type of message that the executor may send.</param>
    /// <exception cref="ArgumentNullException"><paramref name="type"/> is <see langword="null"/>.</exception>
    public SendsMessageAttribute(Type type)
    {
        this.Type = Throw.IfNull(type);
    }
}
