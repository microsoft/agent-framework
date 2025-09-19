// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.Workflows;

/// <summary>
/// Executes a user-provided asynchronous function in response to workflow messages of the specified input type.
/// </summary>
/// <typeparam name="TInput">The type of input message.</typeparam>
/// <param name="handlerAsync">A delegate that defines the asynchronous function to execute for each input message.</param>
/// <param name="id">A optional unique identifier for the executor. If <c>null</c>, a type-tagged UUID will be generated.</param>
/// <param name="options">Configuration options for the executor. If <c>null</c>, default options will be used.</param>
public class FunctionExecutor<TInput>(Func<TInput, IWorkflowContext, CancellationToken, ValueTask> handlerAsync,
        string? id = null,
        ExecutorOptions? options = null) : Executor<TInput>(id, options)
{
    internal static Func<TInput, IWorkflowContext, CancellationToken, ValueTask> WrapAction(Action<TInput, IWorkflowContext, CancellationToken> handlerSync)
    {
        return RunActionAsync;

        ValueTask RunActionAsync(TInput input, IWorkflowContext workflowContext, CancellationToken cancellation)
        {
            handlerSync(input, workflowContext, cancellation);
            return default;
        }
    }

    /// <inheritdoc/>
    public override ValueTask HandleAsync(TInput message, IWorkflowContext context) => handlerAsync(message, context, default);

    /// <summary>
    /// Creates a new instance of the <see cref="FunctionExecutor{TInput}"/> class.
    /// </summary>
    /// <param name="handlerSync">A synchronous function to execute for each input message and workflow context.</param>
    public FunctionExecutor(Action<TInput, IWorkflowContext, CancellationToken> handlerSync) : this(WrapAction(handlerSync))
    {
    }
}

/// <summary>
/// Executes a user-provided asynchronous function in response to workflow messages of the specified input type,
/// </summary>
/// <typeparam name="TInput">The type of input message.</typeparam>
/// <typeparam name="TOutput">The type of output message.</typeparam>
/// <param name="handlerAsync">A delegate that defines the asynchronous function to execute for each input message.</param>
/// <param name="id">A optional unique identifier for the executor. If <c>null</c>, a type-tagged UUID will be generated.</param>
/// <param name="options">Configuration options for the executor. If <c>null</c>, default options will be used.</param>
public class FunctionExecutor<TInput, TOutput>(Func<TInput, IWorkflowContext, CancellationToken, ValueTask<TOutput>> handlerAsync,
        string? id = null,
        ExecutorOptions? options = null) : Executor<TInput, TOutput>(id, options)
{
    internal static Func<TInput, IWorkflowContext, CancellationToken, ValueTask<TOutput>> WrapFunc(Func<TInput, IWorkflowContext, CancellationToken, TOutput> handlerSync)
    {
        return RunFuncAsync;

        ValueTask<TOutput> RunFuncAsync(TInput input, IWorkflowContext workflowContext, CancellationToken cancellation)
        {
            TOutput result = handlerSync(input, workflowContext, cancellation);
            return new ValueTask<TOutput>(result);
        }
    }

    /// <inheritdoc/>
    public override ValueTask<TOutput> HandleAsync(TInput message, IWorkflowContext context) => handlerAsync(message, context, default);

    /// <summary>
    /// Creates a new instance of the <see cref="FunctionExecutor{TInput,TOutput}"/> class.
    /// </summary>
    /// <param name="handlerSync">A synchronous function to execute for each input message and workflow context.</param>
    public FunctionExecutor(Func<TInput, IWorkflowContext, CancellationToken, TOutput> handlerSync) : this(WrapFunc(handlerSync))
    {
    }
}
