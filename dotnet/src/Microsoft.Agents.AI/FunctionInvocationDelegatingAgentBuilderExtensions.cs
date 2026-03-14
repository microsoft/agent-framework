// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides extension methods for configuring and customizing <see cref="AIAgentBuilder"/> instances.
/// </summary>
public static class FunctionInvocationDelegatingAgentBuilderExtensions
{
    /// <summary>
    /// Adds function invocation callbacks to the <see cref="AIAgent"/> pipeline that intercepts and processes <see cref="AIFunction"/> calls.
    /// </summary>
    /// <param name="builder">The <see cref="AIAgentBuilder"/> to which the function invocation callback is added.</param>
    /// <param name="callback">
    /// A delegate that processes function invocations. The delegate receives the <see cref="AIAgent"/> instance,
    /// the function invocation context, and a continuation delegate representing the next callback in the pipeline.
    /// It returns a task representing the result of the function invocation.
    /// </param>
    /// <returns>The <see cref="AIAgentBuilder"/> instance with the function invocation callback added, enabling method chaining.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="builder"/> or <paramref name="callback"/> is <see langword="null"/>.</exception>
    /// <remarks>
    /// <para>
    /// The callback must call the provided continuation delegate to proceed with the function invocation,
    /// unless it intends to completely replace the function's behavior.
    /// </para>
    /// <para>
    /// The inner agent or the pipeline wrapping it must include a <see cref="FunctionInvokingChatClient"/>. If one does not exist,
    /// the <see cref="AIAgent"/> added to the pipline by this method will throw an exception when it is invoked.
    /// </para>
    /// </remarks>
    public static AIAgentBuilder Use(this AIAgentBuilder builder, Func<AIAgent, FunctionInvocationContext, Func<FunctionInvocationContext, CancellationToken, ValueTask<object?>>, CancellationToken, ValueTask<object?>> callback)
    {
        _ = Throw.IfNull(builder);
        _ = Throw.IfNull(callback);
        return builder.Use((innerAgent, _) =>
        {
            // Function calling requires a ChatClientAgent inner agent.
            if (innerAgent.GetService<FunctionInvokingChatClient>() is null)
            {
                throw new InvalidOperationException($"The function invocation middleware can only be used with decorations of a {nameof(AIAgent)} that support usage of FunctionInvokingChatClient decorated chat clients.");
            }

            return new FunctionInvocationDelegatingAgent(innerAgent, callback);
        });
    }
}
