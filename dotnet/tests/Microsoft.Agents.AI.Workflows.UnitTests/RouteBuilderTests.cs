// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using FluentAssertions;
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
        result.Should().NotBeNull();
        result!.IsSuccess.Should().BeTrue();
        result.IsVoid.Should().BeTrue();
        result.Result.Should().BeNull();
        invocation.InvocationCount.Should().Be(1);
        invocation.Message.Should().Be("hello");
        invocation.Context.Should().BeSameAs(context);

        if (UsesCancellationToken(overload))
        {
            invocation.CancellationToken.Should().Be(cancellationToken);
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
        result.Should().NotBeNull();
        result!.IsSuccess.Should().BeTrue();
        result.IsVoid.Should().BeFalse();
        result.Result.Should().Be("HELLO");
        router.DefaultOutputTypes.Should().Contain(typeof(string));
        invocation.InvocationCount.Should().Be(1);
        invocation.Message.Should().Be("hello");
        invocation.Context.Should().BeSameAs(context);

        if (UsesCancellationToken(overload))
        {
            invocation.CancellationToken.Should().Be(cancellationToken);
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
        result.Should().NotBeNull();
        result!.IsSuccess.Should().BeTrue();
        result.IsVoid.Should().BeTrue();
        result.Result.Should().BeNull();
        invocation.InvocationCount.Should().Be(1);
        invocation.Message.Should().BeEquivalentTo(new PortableValue(payload));
        invocation.Context.Should().BeSameAs(context);

        if (UsesCancellationToken(overload))
        {
            invocation.CancellationToken.Should().Be(cancellationToken);
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
        result.Should().NotBeNull();
        result!.IsSuccess.Should().BeTrue();
        result.IsVoid.Should().BeFalse();
        result.Result.Should().Be("HELLO");
        invocation.InvocationCount.Should().Be(1);
        invocation.Message.Should().BeEquivalentTo(new PortableValue(payload));
        invocation.Context.Should().BeSameAs(context);

        if (UsesCancellationToken(overload))
        {
            invocation.CancellationToken.Should().Be(cancellationToken);
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
            return ValueTask.CompletedTask;
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
        voidResult.Should().NotBeNull();
        voidResult!.IsVoid.Should().BeTrue();
        voidInvocation.Message.Should().Be("hello");
        voidInvocation.Context.Should().BeSameAs(context);
        voidInvocation.CancellationToken.Should().Be(cancellationToken);

        typedResult.Should().NotBeNull();
        typedResult!.Result.Should().Be(42);
        router.DefaultOutputTypes.Should().Contain(typeof(int));
        resultInvocation.Message.Should().Be(41);
        resultInvocation.Context.Should().BeSameAs(context);
        resultInvocation.CancellationToken.Should().Be(cancellationToken);
    }

    [Fact]
    public void AddHandler_ForPortableValue_ThrowsInvalidOperationException()
    {
        // Arrange
        RouteBuilder routeBuilder = new(null);

        // Act
        Action act = () => routeBuilder.AddHandler<PortableValue>((message, context) => { });

        // Assert
        act.Should().Throw<InvalidOperationException>()
           .WithMessage("*Use AddCatchAll()*");
    }

    [Fact]
    public void AddHandler_DuplicateRegistrationWithoutOverwrite_ThrowsArgumentException()
    {
        // Arrange
        RouteBuilder routeBuilder = new(null);
        routeBuilder.AddHandler<string>((message, context) => { });

        // Act
        Action act = () => routeBuilder.AddHandler<string>((message, context) => { });

        // Assert
        act.Should().Throw<ArgumentException>()
           .WithMessage("*already registered*");
    }

    [Fact]
    public void AddHandler_OverwriteWithoutExistingRegistration_ThrowsArgumentException()
    {
        // Arrange
        RouteBuilder routeBuilder = new(null);

        // Act
        Action act = () => routeBuilder.AddHandler<string>((message, context) => { }, overwrite: true);

        // Assert
        act.Should().Throw<ArgumentException>()
           .WithMessage("*has not yet been registered*");
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
        context.SentMessages.Should().ContainSingle().Which.Should().Be("second");
    }

    [Fact]
    public void AddCatchAll_DuplicateRegistrationWithoutOverwrite_ThrowsInvalidOperationException()
    {
        // Arrange
        RouteBuilder routeBuilder = new(null);
        routeBuilder.AddCatchAll((message, context) => { });

        // Act
        Action act = () => routeBuilder.AddCatchAll((message, context) => { });

        // Assert
        act.Should().Throw<InvalidOperationException>()
           .WithMessage("*already registered*");
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
        context.SentMessages.Should().ContainSingle().Which.Should().Be("second");
    }

    [Fact]
    public void AddPortHandler_WithoutExternalRequestContext_ThrowsInvalidOperationException()
    {
        // Arrange
        RouteBuilder routeBuilder = new(null);

        // Act
        Action act = () => routeBuilder.AddPortHandler<string, int>("port", (response, context, cancellationToken) => ValueTask.CompletedTask, out _);

        // Assert
        act.Should().Throw<InvalidOperationException>()
           .WithMessage("*external request context is required*");
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
            return ValueTask.CompletedTask;
        }, out PortBinding portBinding);
        await portBinding.PostRequestAsync("request", requestId: "req-1");
        MessageRouter router = routeBuilder.Build();
        TestWorkflowContext context = new("executor");
        CancellationToken cancellationToken = new CancellationTokenSource().Token;
        ExternalResponse response = externalRequestContext.PostedRequests.Single().CreateResponse(42);

        // Act
        CallResult? result = await router.RouteMessageAsync(response, context, cancellationToken: cancellationToken);

        // Assert
        externalRequestContext.RegisteredPorts.Should().ContainSingle(port => port.Id == "port");
        externalRequestContext.PostedRequests.Should().ContainSingle(request => request.RequestId == "req-1");
        result.Should().NotBeNull();
        result!.IsSuccess.Should().BeTrue();
        result.Result.Should().BeSameAs(response);
        invocation.InvocationCount.Should().Be(1);
        invocation.Message.Should().Be(42);
        invocation.Context.Should().BeSameAs(context);
        invocation.CancellationToken.Should().Be(cancellationToken);
    }

    [Fact]
    public async Task AddPortHandler_UnknownPort_ReturnsExceptionResultAsync()
    {
        // Arrange
        TestExternalRequestContext externalRequestContext = new();
        RouteBuilder routeBuilder = new(externalRequestContext);
        routeBuilder.AddPortHandler<string, int>("port", (response, context, cancellationToken) => ValueTask.CompletedTask, out _);
        MessageRouter router = routeBuilder.Build();
        ExternalRequest request = ExternalRequest.Create(RequestPort.Create<string, int>("other"), "request", requestId: "req-1");

        // Act
        CallResult? result = await router.RouteMessageAsync(request.CreateResponse(42), new TestWorkflowContext("executor"));

        // Assert
        result.Should().NotBeNull();
        result!.IsSuccess.Should().BeFalse();
        result.Exception.Should().BeOfType<InvalidOperationException>();
        result.Exception!.Message.Should().Contain("Unknown port");
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
                    return ValueTask.CompletedTask;
                });
                break;
            case HandlerOverload.AsyncWithoutCancellation:
                routeBuilder.AddHandler<string>((message, context) =>
                {
                    invocation.Capture(message, context);
                    return ValueTask.CompletedTask;
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
                    return ValueTask.FromResult(NormalizeHandlerResult(message));
                };
                routeBuilder.AddHandler<string, string>(asyncHandlerWithCancellation);
                break;
            case HandlerOverload.AsyncWithoutCancellation:
                Func<string, IWorkflowContext, ValueTask<string>> asyncHandler = (message, context) =>
                {
                    invocation.Capture(message, context);
                    return ValueTask.FromResult(NormalizeHandlerResult(message));
                };
                routeBuilder.AddHandler<string, string>(asyncHandler);
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
                    return ValueTask.CompletedTask;
                });
                break;
            case HandlerOverload.AsyncWithoutCancellation:
                routeBuilder.AddCatchAll((message, context) =>
                {
                    invocation.Capture(message, context);
                    return ValueTask.CompletedTask;
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
                routeBuilder.AddCatchAll<string>((message, context, cancellationToken) =>
                {
                    invocation.Capture(message, context, cancellationToken);
                    return NormalizeCatchAllResult(message);
                });
                break;
            case HandlerOverload.SyncWithoutCancellation:
                routeBuilder.AddCatchAll<string>((message, context) =>
                {
                    invocation.Capture(message, context);
                    return NormalizeCatchAllResult(message);
                });
                break;
            case HandlerOverload.AsyncWithCancellation:
                Func<PortableValue, IWorkflowContext, CancellationToken, ValueTask<string>> asyncCatchAllWithCancellation = (message, context, cancellationToken) =>
                {
                    invocation.Capture(message, context, cancellationToken);
                    return ValueTask.FromResult(NormalizeCatchAllResult(message));
                };
                routeBuilder.AddCatchAll<string>(asyncCatchAllWithCancellation);
                break;
            case HandlerOverload.AsyncWithoutCancellation:
                Func<PortableValue, IWorkflowContext, ValueTask<string>> asyncCatchAll = (message, context) =>
                {
                    invocation.Capture(message, context);
                    return ValueTask.FromResult(NormalizeCatchAllResult(message));
                };
                routeBuilder.AddCatchAll<string>(asyncCatchAll);
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
