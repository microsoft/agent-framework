// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides extension methods for configuring an <see cref="AIAgentBuilder"/> instance.
/// </summary>
/// <remarks>This class contains methods that extend the functionality of the <see cref="AIAgentBuilder"/>  to
/// allow additional customization and behavior injection.</remarks>
public static class AIAgentBuilderExtensions
{
    /// <summary>
    /// Adds a middleware to the AI agent pipeline that intercepts and processes <see cref="AIFunction"/> invocations.
    /// </summary>
    /// <param name="builder">The <see cref="AIAgentBuilder"/> to which the middleware is added.</param>
    /// <param name="callback">A delegate that processes function invocations. The delegate receives the invocation context, the next
    /// middleware in the pipeline, and a cancellation token, and returns a task representing the result of the
    /// invocation.</param>
    /// <returns>The <see cref="AIAgentBuilder"/> instance with the middleware added.</returns>
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
