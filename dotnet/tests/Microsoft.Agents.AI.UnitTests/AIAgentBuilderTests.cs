// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Moq;

namespace Microsoft.Agents.AI.UnitTests;

/// <summary>
/// Unit tests for the <see cref="AIAgentBuilder"/> class.
/// </summary>
public class AIAgentBuilderTests
{
    /// <summary>
    /// Verify that constructor throws ArgumentNullException when innerAgent is null.
    /// </summary>
    [Fact]
    public void Constructor_WithNullInnerAgent_ThrowsArgumentNullException()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>("innerAgent", () => new AIAgentBuilder((AIAgent)null!));
    }

    /// <summary>
    /// Verify that constructor throws ArgumentNullException when innerAgentFactory is null.
    /// </summary>
    [Fact]
    public void Constructor_WithNullInnerAgentFactory_ThrowsArgumentNullException()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>("innerAgentFactory", () => new AIAgentBuilder((Func<IServiceProvider, AIAgent>)null!));
    }

    /// <summary>
    /// Verify that Build returns the inner agent when no middleware is added.
    /// </summary>
    [Fact]
    public void Build_WithNoMiddleware_ReturnsInnerAgent()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        var builder = new AIAgentBuilder(mockAgent.Object);

        // Act
        var result = builder.Build();

        // Assert
        Assert.Same(mockAgent.Object, result);
    }

    /// <summary>
    /// Verify that Build works with factory function.
    /// </summary>
    [Fact]
    public void Build_WithFactory_ReturnsAgentFromFactory()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        var builder = new AIAgentBuilder(_ => mockAgent.Object);

        // Act
        var result = builder.Build();

        // Assert
        Assert.Same(mockAgent.Object, result);
    }

    /// <summary>
    /// Verify that Use with simple factory works correctly.
    /// </summary>
    [Fact]
    public void Use_WithSimpleFactory_AppliesMiddleware()
    {
        // Arrange
        var mockInnerAgent = new Mock<AIAgent>();
        var mockOuterAgent = new Mock<AIAgent>();
        var builder = new AIAgentBuilder(mockInnerAgent.Object);

        // Act
        var result = builder.Use(innerAgent =>
        {
            Assert.Same(mockInnerAgent.Object, innerAgent);
            return mockOuterAgent.Object;
        }).Build();

        // Assert
        Assert.Same(mockOuterAgent.Object, result);
    }

    /// <summary>
    /// Verify that Use with service provider factory works correctly.
    /// </summary>
    [Fact]
    public void Use_WithServiceProviderFactory_AppliesMiddleware()
    {
        // Arrange
        var mockInnerAgent = new Mock<AIAgent>();
        var mockOuterAgent = new Mock<AIAgent>();
        var mockServiceProvider = new Mock<IServiceProvider>();
        var builder = new AIAgentBuilder(mockInnerAgent.Object);

        // Act
        var result = builder.Use((innerAgent, services) =>
        {
            Assert.Same(mockInnerAgent.Object, innerAgent);
            Assert.NotNull(services);
            return mockOuterAgent.Object;
        }).Build(mockServiceProvider.Object);

        // Assert
        Assert.Same(mockOuterAgent.Object, result);
    }

    /// <summary>
    /// Verify that multiple middleware are applied in correct order (first added is outermost).
    /// </summary>
    [Fact]
    public void Use_WithMultipleMiddleware_AppliesInCorrectOrder()
    {
        // Arrange
        var mockInnerAgent = new Mock<AIAgent>();
        var mockMiddleAgent = new Mock<AIAgent>();
        var mockOuterAgent = new Mock<AIAgent>();
        var builder = new AIAgentBuilder(mockInnerAgent.Object);

        // Act
        var result = builder
            .Use(innerAgent =>
            {
                // First middleware added (will be outermost) - should receive result of second middleware
                Assert.Same(mockMiddleAgent.Object, innerAgent);
                return mockOuterAgent.Object;
            })
            .Use(innerAgent =>
            {
                // Second middleware added (will be applied first) - should receive the original inner agent
                Assert.Same(mockInnerAgent.Object, innerAgent);
                return mockMiddleAgent.Object;
            })
            .Build();

        // Assert
        // The result should be from the first middleware since it's the outermost
        Assert.Same(mockOuterAgent.Object, result);
    }

    /// <summary>
    /// Verify that Use throws ArgumentNullException when agentFactory is null.
    /// </summary>
    [Fact]
    public void Use_WithNullSimpleFactory_ThrowsArgumentNullException()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        var builder = new AIAgentBuilder(mockAgent.Object);

        // Act & Assert
        Assert.Throws<ArgumentNullException>("agentFactory", () => builder.Use((Func<AIAgent, AIAgent>)null!));
    }

    /// <summary>
    /// Verify that Use throws ArgumentNullException when agentFactory with service provider is null.
    /// </summary>
    [Fact]
    public void Use_WithNullServiceProviderFactory_ThrowsArgumentNullException()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        var builder = new AIAgentBuilder(mockAgent.Object);

        // Act & Assert
        Assert.Throws<ArgumentNullException>("agentFactory", () => builder.Use((Func<AIAgent, IServiceProvider, AIAgent>)null!));
    }

    /// <summary>
    /// Verify that Build throws InvalidOperationException when middleware returns null.
    /// </summary>
    [Fact]
    public void Build_WithMiddlewareReturningNull_ThrowsInvalidOperationException()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        var builder = new AIAgentBuilder(mockAgent.Object);

        // Act & Assert
        var exception = Assert.Throws<InvalidOperationException>(() =>
            builder.Use(_ => null!).Build());

        Assert.Contains("returned null", exception.Message);
        Assert.Contains("AIAgentBuilder", exception.Message);
    }

    /// <summary>
    /// Verify that Build uses EmptyServiceProvider when services is null.
    /// </summary>
    [Fact]
    public void Build_WithNullServices_UsesEmptyServiceProvider()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        var builder = new AIAgentBuilder(mockAgent.Object);
        IServiceProvider? capturedServices = null;

        // Act
        builder.Use((agent, services) =>
        {
            capturedServices = services;
            return agent;
        }).Build(null);

        // Assert
        Assert.NotNull(capturedServices);
        Assert.Null(capturedServices.GetService(typeof(string))); // EmptyServiceProvider returns null for everything
    }

    /// <summary>
    /// Verify that service provider is passed correctly to factories.
    /// </summary>
    [Fact]
    public void PassesServiceProviderToFactories()
    {
        // Arrange
        var expectedServiceProvider = new ServiceCollection().BuildServiceProvider();
        var mockInnerAgent = new Mock<AIAgent>();
        var mockOuterAgent = new Mock<AIAgent>();

        var builder = new AIAgentBuilder(services =>
        {
            Assert.Same(expectedServiceProvider, services);
            return mockInnerAgent.Object;
        });

        builder.Use((innerAgent, serviceProvider) =>
        {
            Assert.Same(expectedServiceProvider, serviceProvider);
            Assert.Same(mockInnerAgent.Object, innerAgent);
            return mockOuterAgent.Object;
        });

        // Act
        var result = builder.Build(expectedServiceProvider);

        // Assert
        Assert.Same(mockOuterAgent.Object, result);
    }

    /// <summary>
    /// Verify that pipeline is built in the order added (first added is outermost).
    /// </summary>
    [Fact]
    public void BuildsPipelineInOrderAdded()
    {
        // Arrange
        var mockInnerAgent = new Mock<AIAgent>();
        var builder = new AIAgentBuilder(mockInnerAgent.Object)
            .Use(next => new InnerAgentCapturingAgent("First", next))
            .Use(next => new InnerAgentCapturingAgent("Second", next))
            .Use(next => new InnerAgentCapturingAgent("Third", next));

        // Act
        var first = (InnerAgentCapturingAgent)builder.Build();

        // Assert
        Assert.Equal("First", first.TestName);
        var second = (InnerAgentCapturingAgent)first.InnerAgent;
        Assert.Equal("Second", second.TestName);
        var third = (InnerAgentCapturingAgent)second.InnerAgent;
        Assert.Equal("Third", third.TestName);
        Assert.Same(mockInnerAgent.Object, third.InnerAgent);
    }

    /// <summary>
    /// Verify that factories cannot return null.
    /// </summary>
    [Fact]
    public void DoesNotAllowFactoriesToReturnNull()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        var builder = new AIAgentBuilder(mockAgent.Object);
        builder.Use(_ => null!);

        // Act & Assert
        var ex = Assert.Throws<InvalidOperationException>(() => builder.Build());
        Assert.Contains("entry at index 0", ex.Message);
    }

    /// <summary>
    /// Verify that EmptyServiceProvider is used when no services are provided and supports keyed services.
    /// </summary>
    [Fact]
    public void UsesEmptyServiceProviderWhenNoServicesProvided()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        var builder = new AIAgentBuilder(mockAgent.Object);

        // Act & Assert
        builder.Use((innerAgent, serviceProvider) =>
        {
            Assert.Null(serviceProvider.GetService(typeof(object)));

            var keyedServiceProvider = Assert.IsType<IKeyedServiceProvider>(serviceProvider, exactMatch: false);
            Assert.Null(keyedServiceProvider.GetKeyedService(typeof(object), "key"));
            Assert.Throws<InvalidOperationException>(() => keyedServiceProvider.GetRequiredKeyedService(typeof(object), "key"));

            return innerAgent;
        });
        builder.Build();
    }

    #region Delegate Overload Tests

    /// <summary>
    /// Verify that Use with shared delegate throws ArgumentNullException when sharedFunc is null.
    /// </summary>
    [Fact]
    public void Use_WithNullSharedFunc_ThrowsArgumentNullException()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        var builder = new AIAgentBuilder(mockAgent.Object);

        // Act & Assert
        Assert.Throws<ArgumentNullException>("sharedFunc", () =>
            builder.Use((Func<IEnumerable<ChatMessage>, AgentThread?, AgentRunOptions?, Func<IEnumerable<ChatMessage>, AgentThread?, AgentRunOptions?, CancellationToken, Task>, CancellationToken, Task>)null!));
    }

    /// <summary>
    /// Verify that Use with both delegates null throws ArgumentNullException.
    /// </summary>
    [Fact]
    public void Use_WithBothDelegatesNull_ThrowsArgumentNullException()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        var builder = new AIAgentBuilder(mockAgent.Object);

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            builder.Use(null, null));

        Assert.Contains("runFunc", exception.Message);
    }

    /// <summary>
    /// Verify that Use with shared delegate creates AnonymousDelegatingAIAgent.
    /// </summary>
    [Fact]
    public void Use_WithSharedDelegate_CreatesAnonymousDelegatingAgent()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        var builder = new AIAgentBuilder(mockAgent.Object);

        // Act
        var result = builder.Use((_, _, _, _, _) => Task.CompletedTask).Build();

        // Assert
        Assert.IsType<AnonymousDelegatingAIAgent>(result);
    }

    /// <summary>
    /// Verify that Use with runFunc only creates AnonymousDelegatingAIAgent.
    /// </summary>
    [Fact]
    public void Use_WithRunFuncOnly_CreatesAnonymousDelegatingAgent()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        var builder = new AIAgentBuilder(mockAgent.Object);

        // Act
        var result = builder.Use((_, _, _, _, _) => Task.FromResult(new AgentRunResponse()), null).Build();

        // Assert
        Assert.IsType<AnonymousDelegatingAIAgent>(result);
    }

    /// <summary>
    /// Verify that Use with runStreamingFunc only creates AnonymousDelegatingAIAgent.
    /// </summary>
    [Fact]
    public void Use_WithStreamingFuncOnly_CreatesAnonymousDelegatingAgent()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        var builder = new AIAgentBuilder(mockAgent.Object);

        // Act
        var result = builder.Use(null, (_, _, _, _, _) => AsyncEnumerable.Empty<AgentRunResponseUpdate>()).Build();

        // Assert
        Assert.IsType<AnonymousDelegatingAIAgent>(result);
    }

    /// <summary>
    /// Verify that Use with both delegates creates AnonymousDelegatingAIAgent.
    /// </summary>
    [Fact]
    public void Use_WithBothDelegates_CreatesAnonymousDelegatingAgent()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        var builder = new AIAgentBuilder(mockAgent.Object);

        // Act
        var result = builder.Use(
            (_, _, _, _, _) => Task.FromResult(new AgentRunResponse()),
            (_, _, _, _, _) => AsyncEnumerable.Empty<AgentRunResponseUpdate>()).Build();

        // Assert
        Assert.IsType<AnonymousDelegatingAIAgent>(result);
    }

    #endregion

    /// <summary>
    /// Helper class for testing pipeline order.
    /// </summary>
    private sealed class InnerAgentCapturingAgent : DelegatingAIAgent
    {
        public string TestName { get; }
        public new AIAgent InnerAgent => base.InnerAgent;

        public InnerAgentCapturingAgent(string name, AIAgent innerAgent) : base(innerAgent)
        {
            this.TestName = name;
        }
    }
}
