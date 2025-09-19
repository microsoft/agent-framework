// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using System.Reflection;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Execution;

namespace Microsoft.Agents.Workflows.Reflection;

internal readonly struct MessageHandlerInfo
{
    public Type InType { get; init; }
    public Type? OutType { get; init; }

    public MethodInfo HandlerInfo { get; init; }
    public Func<object, ValueTask<object?>>? Unwrapper { get; init; }

    public MessageHandlerInfo(MethodInfo handlerInfo)
    {
        // The method is one of the following:
        //   - ValueTask HandleAsync(TMessage message, IExecutionContext context)
        //   - ValueTask<TResult> HandleAsync(TMessage message, IExecutionContext context)
        this.HandlerInfo = handlerInfo;

        ParameterInfo[] parameters = handlerInfo.GetParameters();
        if (parameters.Length != 2)
        {
            throw new ArgumentException("Handler method must have exactly two parameters: TMessage and IExecutionContext.", nameof(handlerInfo));
        }

        if (parameters[1].ParameterType != typeof(IWorkflowContext))
        {
            throw new ArgumentException("Handler method's second parameter must be of type IExecutionContext.", nameof(handlerInfo));
        }

        this.InType = parameters[0].ParameterType;

        Type decoratedReturnType = handlerInfo.ReturnType;
        if (decoratedReturnType.IsGenericType && decoratedReturnType.GetGenericTypeDefinition() == typeof(ValueTask<>))
        {
            // If the return type is ValueTask<TResult>, extract TResult.
            Type[] returnRawTypes = decoratedReturnType.GetGenericArguments();
            Debug.Assert(
                returnRawTypes.Length == 1,
                "ValueTask<TResult> should have exactly one generic argument.");

            this.OutType = returnRawTypes.Single();
            this.Unwrapper = ValueTaskTypeErasure.UnwrapperFor(this.OutType);
        }
        else if (decoratedReturnType == typeof(ValueTask))
        {
            // If the return type is ValueTask, there is no output type.
            this.OutType = null;
        }
        else
        {
            throw new ArgumentException("Handler method must return ValueTask or ValueTask<TResult>.", nameof(handlerInfo));
        }
    }

    public static Func<object, IWorkflowContext, ValueTask<CallResult>> Bind(Func<object, IWorkflowContext, object?> handlerAsync, bool checkType, Type? resultType = null, Func<object, ValueTask<object?>>? unwrapper = null)
    {
        return InvokeHandlerAsync;

        async ValueTask<CallResult> InvokeHandlerAsync(object message, IWorkflowContext workflowContext)
        {
            bool expectingVoid = resultType is null || resultType == typeof(void);

            try
            {
                object? maybeValueTask = handlerAsync(message, workflowContext);

                if (expectingVoid)
                {
                    if (maybeValueTask is ValueTask vt)
                    {
                        await vt.ConfigureAwait(false);
                        return CallResult.ReturnVoid();
                    }

                    throw new InvalidOperationException(
                        "Handler method is expected to return ValueTask or ValueTask<TResult>, but returned " +
                        $"{maybeValueTask?.GetType().Name ?? "null"}.");
                }

                Debug.Assert(resultType is not null, "Expected resultType to be non-null when not expecting void.");
                if (unwrapper is null)
                {
                    throw new InvalidOperationException(
                        $"Handler method is expected to return ValueTask<{resultType!.Name}>, but no unwrapper is available.");
                }

                if (maybeValueTask is null)
                {
                    throw new InvalidOperationException(
                        $"Handler method returned null, but a ValueTask<{resultType!.Name}> was expected.");
                }

                object? result = await unwrapper(maybeValueTask).ConfigureAwait(false);

                if (checkType && result is not null && !resultType.IsInstanceOfType(result))
                {
                    throw new InvalidOperationException(
                        $"Handler method returned an incompatible type: expected {resultType.Name}, got {result.GetType().Name}.");
                }

                return CallResult.ReturnResult(result);
            }
            catch (Exception ex)
            {
                // If the handler throws an exception, return it in the CallResult.
                return CallResult.RaisedException(wasVoid: expectingVoid, exception: ex);
            }
        }
    }

    public Func<object, IWorkflowContext, ValueTask<CallResult>> Bind<
        [DynamicallyAccessedMembers(
            ReflectionDemands.RuntimeInterfaceDiscoveryAndInvocation)
        ] TExecutor
        >
        (ReflectingExecutor<TExecutor> executor, bool checkType = false)
        where TExecutor : ReflectingExecutor<TExecutor>
    {
        MethodInfo handlerMethod = this.HandlerInfo;
        return Bind(InvokeHandler, checkType, this.OutType, this.Unwrapper);

        object? InvokeHandler(object message, IWorkflowContext workflowContext)
        {
            return handlerMethod.Invoke(executor, [message, workflowContext]);
        }
    }
}
