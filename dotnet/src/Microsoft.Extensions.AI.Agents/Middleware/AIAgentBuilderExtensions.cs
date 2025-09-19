// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Provides extension methods for configuring an <see cref="AIAgentBuilder"/> instance.
/// </summary>
/// <remarks>This class contains methods that extend the functionality of the <see cref="AIAgentBuilder"/>  to
/// allow additional customization and behavior injection.</remarks>
public static class AIAgentBuilderExtensions
{
    /// <summary>
    /// Adds a middleware to the AI agent pipeline that intercepts and processes agent running invocation operations.
    /// </summary>
    /// <param name="builder">The <see cref="AIAgentBuilder"/> to which the middleware is added.</param>
    /// <param name="callback">A delegate that processes agent running invocations. The delegate takes the current <see
    /// cref="AgentRunContext"/> and a function representing the next core agent invocation, and
    /// returns a <see cref="Task"/> that completes when the callback finished processing.</param>
    /// <returns>The <see cref="AIAgentBuilder"/> instance, allowing for further configuration of the pipeline.</returns>
    public static AIAgentBuilder UseRunningContext(this AIAgentBuilder builder, Func<AgentRunContext, Func<AgentRunContext, Task>, Task> callback)
    {
        _ = Throw.IfNull(builder);
        _ = Throw.IfNull(callback);
        return Use(builder, callback);
    }

    /// <summary>
    /// Adds a middleware to the AI agent pipeline that intercepts and processes agent running invocation operations.
    /// </summary>
    /// <param name="builder">The <see cref="AIAgentBuilder"/> to which the middleware is added.</param>
    /// <param name="callback">A delegate that processes agent running invocations. The delegate takes the current <see
    /// cref="AgentRunContext"/> and a function representing the next core agent invocation, and
    /// returns a <see cref="Task"/> that completes when the callback finished processing.</param>
    /// <returns>The <see cref="AIAgentBuilder"/> instance, allowing for further configuration of the pipeline.</returns>
    public static AIAgentBuilder Use(this AIAgentBuilder builder, Func<AgentRunContext, Func<AgentRunContext, Task>, Task> callback)
    {
        _ = Throw.IfNull(builder);
        _ = Throw.IfNull(callback);
        return builder.Use((innerAgent, _) => new RunningMiddlewareAgent(innerAgent, callback));
    }

    /// <summary>
    /// Adds a middleware to the AI agent pipeline that intercepts and processes <see cref="AIFunction"/> invocations.
    /// </summary>
    /// <param name="builder">The <see cref="AIAgentBuilder"/> to which the middleware is added.</param>
    /// <param name="callback">A delegate that processes function invocations. The delegate receives the invocation context, the next
    /// middleware in the pipeline, and a cancellation token, and returns a task representing the result of the
    /// invocation.</param>
    /// <returns>The <see cref="AIAgentBuilder"/> instance with the middleware added.</returns>
    public static AIAgentBuilder UseFunctionInvocationContext(this AIAgentBuilder builder, Func<AgentFunctionInvocationContext, Func<AgentFunctionInvocationContext, Task>, Task> callback)
    {
        _ = Throw.IfNull(builder);
        _ = Throw.IfNull(callback);
        return builder.Use((innerAgent, _) =>
        {
            // Function calling requires a ChatClientAgent inner agent.
            if (innerAgent.GetService<ChatClientAgent>() is null)
            {
                throw new InvalidOperationException($"The {nameof(FunctionCallMiddlewareAgent)} can only be used with agents that are decorations of a {nameof(ChatClientAgent)}.");
            }

            return new FunctionCallMiddlewareAgent(innerAgent, callback);
        });
    }

    /// <summary>
    /// Adds a middleware to the AI agent pipeline that intercepts and processes <see cref="AIFunction"/> invocations.
    /// </summary>
    /// <param name="builder">The <see cref="AIAgentBuilder"/> to which the middleware is added.</param>
    /// <param name="callback">A delegate that processes function invocations. The delegate receives the invocation context, the next
    /// middleware in the pipeline, and a cancellation token, and returns a task representing the result of the
    /// invocation.</param>
    /// <returns>The <see cref="AIAgentBuilder"/> instance with the middleware added.</returns>
    public static AIAgentBuilder Use(this AIAgentBuilder builder, Func<AgentFunctionInvocationContext, Func<AgentFunctionInvocationContext, Task>, Task> callback)
    {
        _ = Throw.IfNull(builder);
        _ = Throw.IfNull(callback);
        return builder.Use((innerAgent, _) =>
        {
            // Function calling requires a ChatClientAgent inner agent.
            if (innerAgent.GetService<ChatClientAgent>() is null)
            {
                throw new InvalidOperationException($"The {nameof(FunctionCallMiddlewareAgent)} can only be used with agents that are decorations of a {nameof(ChatClientAgent)}.");
            }

            return new FunctionCallMiddlewareAgent(innerAgent, callback);
        });
    }
}
