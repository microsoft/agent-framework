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
/// [YieldsOutput(typeof(FinalResult))]
/// [YieldsOutput(typeof(StreamChunk))]
/// public partial class MyExecutor : Executor
/// {
///     // ...
/// }
/// </code>
/// </example>
[AttributeUsage(AttributeTargets.Class | AttributeTargets.Method, AllowMultiple = true, Inherited = true)]
public sealed class YieldsOutputAttribute : Attribute
{
    /// <summary>
    /// Gets the type of message that the executor may yield.
    /// </summary>
    public Type Type { get; }

    /// <summary>
    /// Initializes a new instance of the <see cref="YieldsOutputAttribute"/> class.
    /// </summary>
    /// <param name="type">The type of message that the executor may yield.</param>
    /// <exception cref="ArgumentNullException"><paramref name="type"/> is <see langword="null"/>.</exception>
    public YieldsOutputAttribute(Type type)
    {
        this.Type = Throw.IfNull(type);
    }
}
