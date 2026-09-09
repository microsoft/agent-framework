// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Execution;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

public sealed class RouteBuilderTests
{
    public enum HandlerOverload
    {
        SyncWithCancellation = 0,
        SyncWithoutCancellation = 1,
        AsyncWithCancellation = 2,
        AsyncWithoutCancellation = 3,
    }

    private sealed record TestPayload(string Value);

    private sealed class HandlerInvocation
    {
        public object? Message { get; private set; }

        public IWorkflowContext? Context { get; private set; }

        public CancellationToken CancellationToken { get; private set; }

        public int InvocationCount { get; private set; }

        public void Capture(object? message, IWorkflowContext context, CancellationToken cancellationToken = default)
        {
            this.Message = message;
            this.Context = context;
            this.CancellationToken = cancellationToken;
            this.InvocationCount++;
        }
    }

    private sealed class TestExternalRequestContext : IExternalRequestContext, IExternalRequestSink
    {
        public List<RequestPort> RegisteredPorts { get; } = [];

        public List<ExternalRequest> PostedRequests { get; } = [];

        public IExternalRequestSink RegisterPort(RequestPort port)
        {
            this.RegisteredPorts.Add(port);
            return this;
        }

        public ValueTask PostAsync(ExternalRequest request)
        {
            this.PostedRequests.Add(request);
            return default;
        }
    }

    [Theory]
    [InlineData(HandlerOverload.SyncWithCancellation)]
    [InlineData(HandlerOverload.SyncWithoutCancellation)]
    [InlineData(HandlerOverload.AsyncWithCancellation)]
    [InlineData(HandlerOverload.AsyncWithoutCancellation)]
    public async Task AddHandler_VoidOverloads_RouteExpectedMessageAsync(HandlerOverload overload)
    {
        // Arrange
        RouteBuilder routeBuilder = new(null);
        HandlerInvocation invocation = new();
        CancellationToken cancellationToken = new CancellationTokenSource().Token;
        RegisterVoidHandler(routeBuilder, invocation, overload);
        MessageRouter router = routeBuilder.Build();
        TestWorkflowContext context = new("executor");

        // Act
        CallResult? result = await router.RouteMessageAsync("hello", context, cancellationToken: cancellationToken);

        // Assert
        Assert.NotNull(result);
        Assert.True(result!.IsSuccess);
        Assert.True(result.IsVoid);
        Assert.Null(result.Result);
        Assert.Equal(1, invocation.InvocationCount);
        Assert.Equal("hello", invocation.Message);
        Assert.Same(context, invocation.Context);

        if (UsesCancellationToken(overload))
        {
            Assert.Equal(cancellationToken, invocation.CancellationToken);
        }
    }

    [Theory]
    [InlineData(HandlerOverload.SyncWithCancellation)]
    [InlineData(HandlerOverload.SyncWithoutCancellation)]
    [InlineData(HandlerOverload.AsyncWithCancellation)]
    [InlineData(HandlerOverload.AsyncWithoutCancellation)]
    public async Task AddHandler_ResultOverloads_RouteExpectedMessageAsync(HandlerOverload overload)
    {
        // Arrange
        RouteBuilder routeBuilder = new(null);
        HandlerInvocation invocation = new();
        CancellationToken cancellationToken = new CancellationTokenSource().Token;
        RegisterResultHandler(routeBuilder, invocation, overload);
        MessageRouter router = routeBuilder.Build();
        TestWorkflowContext context = new("executor");

        // Act
        CallResult? result = await router.RouteMessageAsync("hello", context, cancellationToken: cancellationToken);

        // Assert
        Assert.NotNull(result);
        Assert.True(result!.IsSuccess);
        Assert.False(result.IsVoid);
        Assert.Equal("HELLO", result.Result);
        Assert.Contains(typeof(string), router.DefaultOutputTypes);
        Assert.Equal(1, invocation.InvocationCount);
        Assert.Equal("hello", invocation.Message);
        Assert.Same(context, invocation.Context);

        if (UsesCancellationToken(overload))
        {
            Assert.Equal(cancellationToken, invocation.CancellationToken);
        }
    }

    [Theory]
    [InlineData(HandlerOverload.SyncWithCancellation)]
    [InlineData(HandlerOverload.SyncWithoutCancellation)]
    [InlineData(HandlerOverload.AsyncWithCancellation)]
    [InlineData(HandlerOverload.AsyncWithoutCancellation)]
    public async Task AddCatchAll_VoidOverloads_RouteUnexpectedMessageAsync(HandlerOverload overload)
    {
        // Arrange
        RouteBuilder routeBuilder = new(null);
        HandlerInvocation invocation = new();
        CancellationToken cancellationToken = new CancellationTokenSource().Token;
        TestPayload payload = new("hello");
        RegisterVoidCatchAll(routeBuilder, invocation, overload);
        MessageRouter router = routeBuilder.Build();
        TestWorkflowContext context = new("executor");

        // Act
        CallResult? result = await router.RouteMessageAsync(payload, context, cancellationToken: cancellationToken);

        // Assert
        Assert.NotNull(result);
        Assert.True(result!.IsSuccess);
        Assert.True(result.IsVoid);
        Assert.Null(result.Result);
        Assert.Equal(1, invocation.InvocationCount);
        Assert.Equivalent(new PortableValue(payload), invocation.Message);
        Assert.Same(context, invocation.Context);

        if (UsesCancellationToken(overload))
        {
            Assert.Equal(cancellationToken, invocation.CancellationToken);
        }
    }

    [Theory]
    [InlineData(HandlerOverload.SyncWithCancellation)]
    [InlineData(HandlerOverload.SyncWithoutCancellation)]
    [InlineData(HandlerOverload.AsyncWithCancellation)]
    [InlineData(HandlerOverload.AsyncWithoutCancellation)]
    public async Task AddCatchAll_ResultOverloads_RouteUnexpectedMessageAsync(HandlerOverload overload)
    {
        // Arrange
        RouteBuilder routeBuilder = new(null);
        HandlerInvocation invocation = new();
        CancellationToken cancellationToken = new CancellationTokenSource().Token;
        TestPayload payload = new("hello");
        RegisterResultCatchAll(routeBuilder, invocation, overload);
        MessageRouter router = routeBuilder.Build();
        TestWorkflowContext context = new("executor");

        // Act
        CallResult? result = await router.RouteMessageAsync(payload, context, cancellationToken: cancellationToken);

        // Assert
        Assert.NotNull(result);
        Assert.True(result!.IsSuccess);
        Assert.False(result.IsVoid);
        Assert.Equal("HELLO", result.Result);
        Assert.Equal(1, invocation.InvocationCount);
        Assert.Equivalent(new PortableValue(payload), invocation.Message);
        Assert.Same(context, invocation.Context);

        if (UsesCancellationToken(overload))
        {
            Assert.Equal(cancellationToken, invocation.CancellationToken);
        }
    }

    [Fact]
    public async Task AddHandlerUntyped_VoidAndResultOverloads_RouteExpectedMessageAsync()
    {
        // Arrange
        RouteBuilder routeBuilder = new(null);
        HandlerInvocation voidInvocation = new();
        HandlerInvocation resultInvocation = new();
        CancellationToken cancellationToken = new CancellationTokenSource().Token;
        routeBuilder.AddHandlerUntyped(typeof(string), (message, context, token) =>
        {
            voidInvocation.Capture(message, context, token);
            return default;
        });
        routeBuilder.AddHandlerUntyped<int>(typeof(int), (message, context, token) =>
        {
            resultInvocation.Capture(message, context, token);
            return new((int)message + 1);
        });
        MessageRouter router = routeBuilder.Build();
        TestWorkflowContext context = new("executor");

        // Act
        CallResult? voidResult = await router.RouteMessageAsync("hello", context, cancellationToken: cancellationToken);
        CallResult? typedResult = await router.RouteMessageAsync(41, context, cancellationToken: cancellationToken);

        // Assert
        Assert.NotNull(voidResult);
        Assert.True(voidResult!.IsVoid);
        Assert.Equal("hello", voidInvocation.Message);
        Assert.Same(context, voidInvocation.Context);
        Assert.Equal(cancellationToken, voidInvocation.CancellationToken);

        Assert.NotNull(typedResult);
        Assert.Equal(42, typedResult!.Result);
        Assert.Contains(typeof(int), router.DefaultOutputTypes);
        Assert.Equal(41, resultInvocation.Message);
        Assert.Same(context, resultInvocation.Context);
        Assert.Equal(cancellationToken, resultInvocation.CancellationToken);
    }

    [Fact]
    public void AddHandler_ForPortableValue_ThrowsInvalidOperationException()
    {
        // Arrange
        RouteBuilder routeBuilder = new(null);

        // Act
        void act() => routeBuilder.AddHandler<PortableValue>((message, context) => { });

        // Assert
        Assert.Contains("Use AddCatchAll()", Assert.Throws<InvalidOperationException>(act).Message);
    }

    [Fact]
    public void AddHandler_DuplicateRegistrationWithoutOverwrite_ThrowsArgumentException()
    {
        // Arrange
        RouteBuilder routeBuilder = new(null);
        routeBuilder.AddHandler<string>((message, context) => { });

        // Act
        void act() => routeBuilder.AddHandler<string>((message, context) => { });

        // Assert
        Assert.Contains("already registered", Assert.Throws<ArgumentException>(act).Message);
    }

    [Fact]
    public void AddHandler_OverwriteWithoutExistingRegistration_ThrowsArgumentException()
    {
        // Arrange
        RouteBuilder routeBuilder = new(null);

        // Act
        void act() => routeBuilder.AddHandler<string>((message, context) => { }, overwrite: true);

        // Assert
        Assert.Contains("has not yet been registered", Assert.Throws<ArgumentException>(act).Message);
    }

    [Fact]
    public async Task AddHandler_OverwriteExistingRegistration_RoutesUpdatedHandlerAsync()
    {
        // Arrange
        RouteBuilder routeBuilder = new(null);
        routeBuilder.AddHandler<string>((message, context) => context.SendMessageAsync("first"));
        routeBuilder.AddHandler<string>((message, context) => context.SendMessageAsync("second"), overwrite: true);
        MessageRouter router = routeBuilder.Build();
        TestWorkflowContext context = new("executor");

        // Act
        _ = await router.RouteMessageAsync("hello", context);

        // Assert
        Assert.Equal("second", Assert.Single(context.SentMessages));
    }

    [Fact]
    public void AddCatchAll_DuplicateRegistrationWithoutOverwrite_ThrowsInvalidOperationException()
    {
        // Arrange
        RouteBuilder routeBuilder = new(null);
        routeBuilder.AddCatchAll((message, context) => { });

        // Act
        void act() => routeBuilder.AddCatchAll((message, context) => { });

        // Assert
        Assert.Contains("already registered", Assert.Throws<InvalidOperationException>(act).Message);
    }

    [Fact]
    public async Task AddCatchAll_OverwriteExistingRegistration_RoutesUpdatedHandlerAsync()
    {
        // Arrange
        RouteBuilder routeBuilder = new(null);
        routeBuilder.AddCatchAll((message, context) => context.SendMessageAsync("first"));
        routeBuilder.AddCatchAll((message, context) => context.SendMessageAsync("second"), overwrite: true);
        MessageRouter router = routeBuilder.Build();
        TestWorkflowContext context = new("executor");

        // Act
        _ = await router.RouteMessageAsync(new TestPayload("hello"), context);

        // Assert
        Assert.Equal("second", Assert.Single(context.SentMessages));
    }

    [Fact]
    public void AddPortHandler_WithoutExternalRequestContext_ThrowsInvalidOperationException()
    {
        // Arrange
        RouteBuilder routeBuilder = new(null);

        // Act
        void act() => routeBuilder.AddPortHandler<string, int>("port", (response, context, cancellationToken) => default, out _);

        // Assert
        Assert.Contains("external request context is required", Assert.Throws<InvalidOperationException>(act).Message);
    }

    [Fact]
    public async Task AddPortHandler_RoutesMatchingExternalResponseAsync()
    {
        // Arrange
        TestExternalRequestContext externalRequestContext = new();
        RouteBuilder routeBuilder = new(externalRequestContext);
        HandlerInvocation invocation = new();
        routeBuilder.AddPortHandler<string, int>("port", (response, context, cancellationToken) =>
        {
            invocation.Capture(response, context, cancellationToken);
            return default;
        }, out PortBinding portBinding);
        await portBinding.PostRequestAsync("request", requestId: "req-1");
        MessageRouter router = routeBuilder.Build();
        TestWorkflowContext context = new("executor");
        CancellationToken cancellationToken = new CancellationTokenSource().Token;
        ExternalResponse response = externalRequestContext.PostedRequests.Single().CreateResponse(42);

        // Act
        CallResult? result = await router.RouteMessageAsync(response, context, cancellationToken: cancellationToken);

        // Assert
        Assert.Equal("port", Assert.Single(externalRequestContext.RegisteredPorts).Id);
        Assert.Equal("req-1", Assert.Single(externalRequestContext.PostedRequests).RequestId);
        Assert.NotNull(result);
        Assert.True(result!.IsSuccess);
        Assert.Same(response, result.Result);
        Assert.Equal(1, invocation.InvocationCount);
        Assert.Equal(42, invocation.Message);
        Assert.Same(context, invocation.Context);
        Assert.Equal(cancellationToken, invocation.CancellationToken);
    }

    [Fact]
    public async Task AddPortHandler_UnknownPort_ReturnsExceptionResultAsync()
    {
        // Arrange
        TestExternalRequestContext externalRequestContext = new();
        RouteBuilder routeBuilder = new(externalRequestContext);
        routeBuilder.AddPortHandler<string, int>("port", (response, context, cancellationToken) => default, out _);
        MessageRouter router = routeBuilder.Build();
        ExternalRequest request = ExternalRequest.Create(RequestPort.Create<string, int>("other"), "request", requestId: "req-1");

        // Act
        CallResult? result = await router.RouteMessageAsync(request.CreateResponse(42), new TestWorkflowContext("executor"));

        // Assert
        Assert.NotNull(result);
        Assert.False(result!.IsSuccess);
        InvalidOperationException exception = Assert.IsType<InvalidOperationException>(result.Exception);
        Assert.Contains("Unknown port", exception.Message);
    }

    private static void RegisterVoidHandler(RouteBuilder routeBuilder, HandlerInvocation invocation, HandlerOverload overload)
    {
        switch (overload)
        {
            case HandlerOverload.SyncWithCancellation:
                routeBuilder.AddHandler<string>((message, context, cancellationToken) => invocation.Capture(message, context, cancellationToken));
                break;
            case HandlerOverload.SyncWithoutCancellation:
                routeBuilder.AddHandler<string>((message, context) => invocation.Capture(message, context));
                break;
            case HandlerOverload.AsyncWithCancellation:
                routeBuilder.AddHandler<string>((message, context, cancellationToken) =>
                {
                    invocation.Capture(message, context, cancellationToken);
                    return default;
                });
                break;
            case HandlerOverload.AsyncWithoutCancellation:
                routeBuilder.AddHandler<string>((message, context) =>
                {
                    invocation.Capture(message, context);
                    return default;
                });
                break;
            default:
                throw new ArgumentOutOfRangeException(nameof(overload));
        }
    }

    private static void RegisterResultHandler(RouteBuilder routeBuilder, HandlerInvocation invocation, HandlerOverload overload)
    {
        switch (overload)
        {
            case HandlerOverload.SyncWithCancellation:
                routeBuilder.AddHandler<string, string>((message, context, cancellationToken) =>
                {
                    invocation.Capture(message, context, cancellationToken);
                    return NormalizeHandlerResult(message);
                });
                break;
            case HandlerOverload.SyncWithoutCancellation:
                routeBuilder.AddHandler<string, string>((message, context) =>
                {
                    invocation.Capture(message, context);
                    return NormalizeHandlerResult(message);
                });
                break;
            case HandlerOverload.AsyncWithCancellation:
                Func<string, IWorkflowContext, CancellationToken, ValueTask<string>> asyncHandlerWithCancellation = (message, context, cancellationToken) =>
                {
                    invocation.Capture(message, context, cancellationToken);
                    return new ValueTask<string>(NormalizeHandlerResult(message));
                };
                routeBuilder.AddHandler(asyncHandlerWithCancellation);
                break;
            case HandlerOverload.AsyncWithoutCancellation:
                Func<string, IWorkflowContext, ValueTask<string>> asyncHandler = (message, context) =>
                {
                    invocation.Capture(message, context);
                    return new ValueTask<string>(NormalizeHandlerResult(message));
                };
                routeBuilder.AddHandler(asyncHandler);
                break;
            default:
                throw new ArgumentOutOfRangeException(nameof(overload));
        }
    }

    private static void RegisterVoidCatchAll(RouteBuilder routeBuilder, HandlerInvocation invocation, HandlerOverload overload)
    {
        switch (overload)
        {
            case HandlerOverload.SyncWithCancellation:
                routeBuilder.AddCatchAll((message, context, cancellationToken) => invocation.Capture(message, context, cancellationToken));
                break;
            case HandlerOverload.SyncWithoutCancellation:
                routeBuilder.AddCatchAll((message, context) => invocation.Capture(message, context));
                break;
            case HandlerOverload.AsyncWithCancellation:
                routeBuilder.AddCatchAll((message, context, cancellationToken) =>
                {
                    invocation.Capture(message, context, cancellationToken);
                    return default;
                });
                break;
            case HandlerOverload.AsyncWithoutCancellation:
                routeBuilder.AddCatchAll((message, context) =>
                {
                    invocation.Capture(message, context);
                    return default;
                });
                break;
            default:
                throw new ArgumentOutOfRangeException(nameof(overload));
        }
    }

    private static void RegisterResultCatchAll(RouteBuilder routeBuilder, HandlerInvocation invocation, HandlerOverload overload)
    {
        switch (overload)
        {
            case HandlerOverload.SyncWithCancellation:
                routeBuilder.AddCatchAll((message, context, cancellationToken) =>
                {
                    invocation.Capture(message, context, cancellationToken);
                    return NormalizeCatchAllResult(message);
                });
                break;
            case HandlerOverload.SyncWithoutCancellation:
                routeBuilder.AddCatchAll((message, context) =>
                {
                    invocation.Capture(message, context);
                    return NormalizeCatchAllResult(message);
                });
                break;
            case HandlerOverload.AsyncWithCancellation:
                Func<PortableValue, IWorkflowContext, CancellationToken, ValueTask<string>> asyncCatchAllWithCancellation = (message, context, cancellationToken) =>
                {
                    invocation.Capture(message, context, cancellationToken);
                    return new ValueTask<string>(NormalizeCatchAllResult(message));
                };
                routeBuilder.AddCatchAll(asyncCatchAllWithCancellation);
                break;
            case HandlerOverload.AsyncWithoutCancellation:
                Func<PortableValue, IWorkflowContext, ValueTask<string>> asyncCatchAll = (message, context) =>
                {
                    invocation.Capture(message, context);
                    return new ValueTask<string>(NormalizeCatchAllResult(message));
                };
                routeBuilder.AddCatchAll(asyncCatchAll);
                break;
            default:
                throw new ArgumentOutOfRangeException(nameof(overload));
        }
    }

    private static bool UsesCancellationToken(HandlerOverload overload) =>
        overload is HandlerOverload.SyncWithCancellation or HandlerOverload.AsyncWithCancellation;

    private static string NormalizeHandlerResult(string message) => message.ToUpperInvariant();

    private static string NormalizeCatchAllResult(PortableValue message) => GetPayloadValue(message).ToUpperInvariant();

    private static string GetPayloadValue(PortableValue message)
    {
        return message.As<TestPayload>() is TestPayload payload
            ? payload.Value
            : throw new InvalidOperationException("Expected catch-all message payload to deserialize as TestPayload.");
    }
}
