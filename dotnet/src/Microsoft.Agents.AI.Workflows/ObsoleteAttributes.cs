// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Declares that an executor may yield messages of the specified type as workflow outputs.
/// </summary>
/// <remarks>
/// <para>
/// Apply this attribute to an <see cref="Executor"/> class to declare the types of messages
/// it may yield via <see cref="IWorkflowContext.YieldOutputAsync"/>. This information is used
/// for protocol validation and documentation.
/// </para>
/// <para>
/// This attribute can be applied multiple times to declare multiple output types.
/// It is inherited by derived classes, allowing base executors to declare common output types.
/// </para>
/// </remarks>
/// <example>
/// <code>
/// [YieldsMessage(typeof(FinalResult))]
/// [YieldsMessage(typeof(StreamChunk))]
/// public partial class MyExecutor : Executor
/// {
///     // ...
/// }
/// </code>
/// </example>
[Obsolete("Use YieldsOutput instead. The Code Generator and the runtime attribute-based type mapping ignore this attribute.")]
[AttributeUsage(AttributeTargets.Class, AllowMultiple = true, Inherited = true)]
public sealed class YieldsMessageAttribute : Attribute
{
    /// <summary>
    /// Gets the type of message that the executor may yield.
    /// </summary>
    public Type Type { get; }

    /// <summary>
    /// Initializes a new instance of the <see cref="YieldsMessageAttribute"/> class.
    /// </summary>
    /// <param name="type">The type of message that the executor may yield.</param>
    /// <exception cref="ArgumentNullException"><paramref name="type"/> is <see langword="null"/>.</exception>
    public YieldsMessageAttribute(Type type)
    {
        this.Type = Throw.IfNull(type);
    }
}

/// <summary>
/// This attribute indicates that a message handler streams messages during its execution.
/// </summary>
[Obsolete("This attribute does not do anything. The Code Generator and the runtime attribute-based type mapping ignore this attribute.")]
[AttributeUsage(AttributeTargets.Class | AttributeTargets.Method, AllowMultiple = true)]
public sealed class StreamsMessageAttribute : Attribute
{
    /// <summary>
    /// The type of the message that the handler yields.
    /// </summary>
    public Type Type { get; }

    /// <summary>
    /// Indicates that the message handler yields streaming messages during the course of execution.
    /// </summary>
    public StreamsMessageAttribute(Type type)
    {
        // This attribute is used to mark executors that yield messages.
        this.Type = Throw.IfNull(type);
    }
}
