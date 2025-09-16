// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Extensions.AI.Agents;

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
    public static AIAgentBuilder Use(this AIAgentBuilder builder, Func<AgentFunctionInvocationCallbackContext?, Func<AgentFunctionInvocationCallbackContext, ValueTask<object?>>, CancellationToken, ValueTask<object?>> callback)
    {
        return builder.Use(innerAgent => new FunctionInvokingCallbackHandlerAgent(innerAgent, callback));
    }

    /// <summary>
    /// Adds a middleware to the AI agent pipeline that intercepts and processes agent running invocation operations.
    /// </summary>
    /// <param name="builder">The <see cref="AIAgentBuilder"/> to which the middleware is added.</param>
    /// <param name="callback">A delegate that processes agent running invocations. The delegate takes the current <see
    /// cref="AgentInvokeCallbackContext"/> and a function representing the next core agent invocation, and
    /// returns a <see cref="Task"/> that completes when the callback finished processing.</param>
    /// <returns>The <see cref="AIAgentBuilder"/> instance, allowing for further configuration of the pipeline.</returns>
    public static AIAgentBuilder Use(this AIAgentBuilder builder, Func<AgentInvokeCallbackContext, Func<AgentInvokeCallbackContext, Task>, Task> callback)
    {
        return builder.Use((innerAgent) => new RunningCallbackHandlerAgent(innerAgent, callback));
    }
}
