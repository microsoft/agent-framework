// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Executes a user-provided asynchronous function in response to workflow messages of the specified input type.
/// </summary>
/// <typeparam name="TInput">The type of input message.</typeparam>
/// <param name="id">A unique identifier for the executor.</param>
/// <param name="handlerAsync">A delegate that defines the asynchronous function to execute for each input message.</param>
/// <param name="options">Configuration options for the executor. If <c>null</c>, default options will be used.</param>
/// <param name="declareCrossRunShareable">Declare that this executor may be used simultaneously by multiple runs safely.</param>
public class FunctionExecutor<TInput>(string id,
        Func<TInput, IWorkflowContext, CancellationToken, ValueTask> handlerAsync,
        ExecutorOptions? options = null,
        bool declareCrossRunShareable = false) : Executor<TInput>(id, options, declareCrossRunShareable)
{
    internal static Func<TInput, IWorkflowContext, CancellationToken, ValueTask> WrapAction(Action<TInput, IWorkflowContext, CancellationToken> handlerSync)
    {
        return RunActionAsync;

        ValueTask RunActionAsync(TInput input, IWorkflowContext workflowContext, CancellationToken cancellationToken)
        {
            handlerSync(input, workflowContext, cancellationToken);
            return default;
        }
    }

    /// <inheritdoc/>
    public override ValueTask HandleAsync(TInput message, IWorkflowContext context, CancellationToken cancellationToken) => handlerAsync(message, context, cancellationToken);

    /// <summary>
    /// Creates a new instance of the <see cref="FunctionExecutor{TInput}"/> class.
    /// </summary>
    /// <param name="id">A unique identifier for the executor.</param>
    /// <param name="handlerSync">A synchronous function to execute for each input message and workflow context.</param>
    public FunctionExecutor(string id, Action<TInput, IWorkflowContext, CancellationToken> handlerSync) : this(id, WrapAction(handlerSync))
    {
    }
}

/// <summary>
/// Executes a user-provided asynchronous function in response to workflow messages of the specified input type,
/// </summary>
/// <typeparam name="TInput">The type of input message.</typeparam>
/// <typeparam name="TOutput">The type of output message.</typeparam>
/// <param name="id">A unique identifier for the executor.</param>
/// <param name="handlerAsync">A delegate that defines the asynchronous function to execute for each input message.</param>
/// <param name="options">Configuration options for the executor. If <c>null</c>, default options will be used.</param>
/// <param name="declareCrossRunShareable">Declare that this executor may be used simultaneously by multiple runs safely.</param>
public class FunctionExecutor<TInput, TOutput>(string id,
        Func<TInput, IWorkflowContext, CancellationToken, ValueTask<TOutput>> handlerAsync,
        ExecutorOptions? options = null,
        bool declareCrossRunShareable = false) : Executor<TInput, TOutput>(id, options, declareCrossRunShareable)
{
    internal static Func<TInput, IWorkflowContext, CancellationToken, ValueTask<TOutput>> WrapFunc(Func<TInput, IWorkflowContext, CancellationToken, TOutput> handlerSync)
    {
        return RunFuncAsync;

        ValueTask<TOutput> RunFuncAsync(TInput input, IWorkflowContext workflowContext, CancellationToken cancellationToken)
        {
            TOutput result = handlerSync(input, workflowContext, cancellationToken);
            return new ValueTask<TOutput>(result);
        }
    }

    /// <inheritdoc/>
    public override ValueTask<TOutput> HandleAsync(TInput message, IWorkflowContext context, CancellationToken cancellationToken) => handlerAsync(message, context, cancellationToken);

    /// <summary>
    /// Creates a new instance of the <see cref="FunctionExecutor{TInput,TOutput}"/> class.
    /// </summary>
    /// <param name="id">A unique identifier for the executor.</param>
    /// <param name="handlerSync">A synchronous function to execute for each input message and workflow context.</param>
    public FunctionExecutor(string id, Func<TInput, IWorkflowContext, CancellationToken, TOutput> handlerSync) : this(id, WrapFunc(handlerSync))
    {
    }
}
