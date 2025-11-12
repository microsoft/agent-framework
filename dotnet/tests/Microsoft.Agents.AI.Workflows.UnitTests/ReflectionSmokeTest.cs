// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Execution;
using Microsoft.Agents.AI.Workflows.Reflection;
using Moq;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

public class BaseTestExecutor<TActual>(string id) : ReflectingExecutor<TActual>(id) where TActual : ReflectingExecutor<TActual>
{
    protected void OnInvokedHandler() => this.InvokedHandler = true;

    public bool InvokedHandler
    {
        get;
        private set;
    }
}

public class DefaultHandler() : BaseTestExecutor<DefaultHandler>(nameof(DefaultHandler)), IMessageHandler<object>
{
    public ValueTask HandleAsync(object message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        this.OnInvokedHandler();
        return this.Handler(message, context);
    }

    public Func<object, IWorkflowContext, ValueTask> Handler
    {
        get;
        set;
    } = (message, context) => default;
}

public class TypedHandler<TInput>() : BaseTestExecutor<TypedHandler<TInput>>(nameof(TypedHandler<>)), IMessageHandler<TInput>
{
    public ValueTask HandleAsync(TInput message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        this.OnInvokedHandler();
        return this.Handler(message, context);
    }

    public Func<TInput, IWorkflowContext, ValueTask> Handler
    {
        get;
        set;
    } = (message, context) => default;
}

public class TypedHandlerWithOutput<TInput, TResult>() : BaseTestExecutor<TypedHandlerWithOutput<TInput, TResult>>(nameof(TypedHandlerWithOutput<,>)), IMessageHandler<TInput, TResult>
{
    public ValueTask<TResult> HandleAsync(TInput message, IWorkflowContext context, CancellationToken cancellationToken)
    {
        this.OnInvokedHandler();
        return this.Handler(message, context);
    }
    public Func<TInput, IWorkflowContext, ValueTask<TResult>> Handler
    {
        get;
        set;
    } = (message, context) => default;
}

public class RoutingReflectionTests
{
    private static async ValueTask<CallResult?> RunTestReflectAndRouteMessageAsync<TInput, TE>(BaseTestExecutor<TE> executor, TInput? input = default) where TInput : new() where TE : ReflectingExecutor<TE>
    {
        MessageRouter router = executor.Router;

        Assert.NotNull(router);
        input ??= new();
        Assert.True(router.CanHandle(input.GetType()));
        Assert.True(router.CanHandle(input));

        CallResult? result = await router.RouteMessageAsync(input, Mock.Of<IWorkflowContext>());

        Assert.True(executor.InvokedHandler);

        return result;
    }

    [Fact]
    public async Task Test_ReflectAndExecute_DefaultHandlerAsync()
    {
        DefaultHandler executor = new();

        CallResult? result = await RunTestReflectAndRouteMessageAsync<object, DefaultHandler>(executor);

        Assert.NotNull(result);
        Assert.True(result.IsSuccess);
        Assert.True(result.IsVoid);
    }

    [Fact]
    public async Task Test_ReflectAndExecute_HandlerReturnsVoidAsync()
    {
        TypedHandler<int> executor = new();

        CallResult? result = await RunTestReflectAndRouteMessageAsync<object, TypedHandler<int>>(executor, 3);

        Assert.NotNull(result);
        Assert.True(result.IsSuccess);
        Assert.True(result.IsVoid);
    }

    [Fact]
    public async Task Test_ReflectAndExecute_HandlerReturnsValueAsync()
    {
        TypedHandlerWithOutput<int, string> executor = new()
        {
            Handler = (message, context) => new ValueTask<string>($"{message}")
        };

        const string Expected = "3";
        CallResult? result = await RunTestReflectAndRouteMessageAsync<object, TypedHandlerWithOutput<int, string>>(executor, int.Parse(Expected));

        Assert.NotNull(result);
        Assert.True(result.IsSuccess);
        Assert.False(result.IsVoid);

        Assert.Equal(Expected, result.Result);
    }
}
