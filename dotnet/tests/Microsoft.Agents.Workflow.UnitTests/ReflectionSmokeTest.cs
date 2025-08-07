// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Core;
using Moq;

namespace Microsoft.Agents.Workflows.UnitTests;

public class BaseTestExecutor : Executor
{
    protected void OnInvokedHandler()
    {
        this.InvokedHandler = true;
    }

    public bool InvokedHandler
    {
        get;
        private set;
    } = false;
}

public class DefaultHandler : BaseTestExecutor, IMessageHandler<object>
{
    public ValueTask HandleAsync(object message, IWorkflowContext context)
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

public class TypedHandler<TInput> : BaseTestExecutor, IMessageHandler<TInput>
{
    public ValueTask HandleAsync(TInput message, IWorkflowContext context)
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

public class TypedHandlerWithOutput<TInput, TResult> : BaseTestExecutor, IMessageHandler<TInput, TResult>
{
    public ValueTask<TResult> HandleAsync(TInput message, IWorkflowContext context)
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
    private async ValueTask<CallResult?> RunTestReflectAndRouteMessageAsync<TInput>(BaseTestExecutor executor, TInput? input = default) where TInput : new()
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

        CallResult? result = await this.RunTestReflectAndRouteMessageAsync<object>(executor);

        Assert.NotNull(result);
        Assert.True(result.IsSuccess);
        Assert.True(result.IsVoid);

        await ((IAsyncDisposable)executor).DisposeAsync();
    }

    [Fact]
    public async Task Test_ReflectAndExecute_HandlerReturnsVoidAsync()
    {
        TypedHandler<int> executor = new();

        CallResult? result = await this.RunTestReflectAndRouteMessageAsync<object>(executor, 3);

        Assert.NotNull(result);
        Assert.True(result.IsSuccess);
        Assert.True(result.IsVoid);

        await ((IAsyncDisposable)executor).DisposeAsync();
    }

    [Fact]
    public async Task Test_ReflectAndExecute_HandlerReturnsValueAsync()
    {
        TypedHandlerWithOutput<int, string> executor = new()
        {
            Handler = (message, context) =>
            {
                return new ValueTask<string>($"{message}");
            }
        };

        const string Expected = "3";
        CallResult? result = await this.RunTestReflectAndRouteMessageAsync<object>(executor, int.Parse(Expected));

        Assert.NotNull(result);
        Assert.True(result.IsSuccess);
        Assert.False(result.IsVoid);

        Assert.Equal(Expected, result.Result);

        await ((IAsyncDisposable)executor).DisposeAsync();
    }
}
