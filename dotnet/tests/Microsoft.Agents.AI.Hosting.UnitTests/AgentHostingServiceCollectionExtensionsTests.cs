// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Moq;

namespace Microsoft.Agents.AI.Hosting.UnitTests;

public class AgentHostingServiceCollectionExtensionsTests
{
    [Fact]
    public async Task AIHostAgent_RunAsync_MarksFeatureUsedAsync()
    {
        // Arrange
        var hostAgent = new AIHostAgent(new TestEchoAgent(name: "hosted-agent"), new NoopAgentSessionStore());
        ResetFeatureUsage();

        // Act
        _ = await hostAgent.RunAsync("hello");

        // Assert
        AssertFeatureUsed(71);
    }

    [Fact]
    public async Task AIHostAgent_RunStreamingAsync_MarksOnlyOnEnumerationAsync()
    {
        // Arrange
        var hostAgent = new AIHostAgent(new TestEchoAgent(name: "hosted-agent"), new NoopAgentSessionStore());
        ResetFeatureUsage();

        // Act
        IAsyncEnumerable<AgentResponseUpdate> updates = hostAgent.RunStreamingAsync("hello");

        // Assert
        AssertFeatureNotUsed();
        await foreach (AgentResponseUpdate _ in updates)
        {
        }
        AssertFeatureUsed(71);
    }

    private static void AssertFeatureUsed(int featureIndex)
    {
#pragma warning disable MAAI001
        string userAgent = FeatureUsage.ApplyToUserAgent(string.Empty);
#pragma warning restore MAAI001
        const string Prefix = "(feat=v1.";
        Assert.StartsWith(Prefix, userAgent);
        Assert.EndsWith(")", userAgent);

        string hexMask = userAgent[Prefix.Length..^1];
        int digitOffset = featureIndex / 4;
        Assert.True(hexMask.Length > digitOffset);
        char digit = char.ToLowerInvariant(hexMask[hexMask.Length - digitOffset - 1]);
        int nibble = digit <= '9' ? digit - '0' : digit - 'a' + 10;
        Assert.NotEqual(0, nibble & (1 << (featureIndex & 3)));
    }

    private static void AssertFeatureNotUsed()
    {
#pragma warning disable MAAI001
        Assert.Equal(string.Empty, FeatureUsage.ApplyToUserAgent(string.Empty));
#pragma warning restore MAAI001
    }

    private static void ResetFeatureUsage()
    {
        MethodInfo? reset = typeof(FeatureUsage).GetMethod(
            "ResetStateForTests",
            BindingFlags.Static | BindingFlags.NonPublic);
        Assert.NotNull(reset);
        reset.Invoke(obj: null, parameters: null);
    }

    /// <summary>
    /// Verifies that providing a null builder to AddAIAgent throws an ArgumentNullException.
    /// </summary>
    [Fact]
    public void AddAIAgent_NullBuilder_ThrowsArgumentNullException() => Assert.Throws<ArgumentNullException>(
        () => AgentHostingServiceCollectionExtensions.AddAIAgent(null!, "agent", "instructions"));

    /// <summary>
    /// Verifies that AddAIAgent without chat client key throws ArgumentNullException for null name.
    /// </summary>
    [Fact]
    public void AddAIAgent_NullName_ThrowsArgumentNullException()
    {
        var services = new ServiceCollection();

        var exception = Assert.Throws<ArgumentNullException>(() => services.AddAIAgent(null!, "instructions"));
        Assert.Equal("name", exception.ParamName);
    }

    /// <summary>
    /// Verifies that AddAIAgent without chat client key allows null instructions.
    /// </summary>
    [Fact]
    public void AddAIAgent_NullInstructions_AllowsNull()
    {
        var services = new ServiceCollection();
        var result = services.AddAIAgent("agentName", (string)null!);
        Assert.NotNull(result);
    }

    /// <summary>
    /// Verifies that AddAIAgent with chat client key throws ArgumentNullException for null name.
    /// </summary>
    [Fact]
    public void AddAIAgentWithKey_NullName_ThrowsArgumentNullException()
    {
        var services = new ServiceCollection();
        var exception = Assert.Throws<ArgumentNullException>(() => services.AddAIAgent(null!, "instructions", "key"));
        Assert.Equal("name", exception.ParamName);
    }

    /// <summary>
    /// Verifies that AddAIAgent with chat client key allows null instructions.
    /// </summary>
    [Fact]
    public void AddAIAgentWithKey_NullInstructions_AllowsNull()
    {
        var services = new ServiceCollection();
        var result = services.AddAIAgent("agentName", null, "key");
        Assert.NotNull(result);
    }

    /// <summary>
    /// Verifies that AddAIAgent with factory delegate throws ArgumentNullException for null builder.
    /// </summary>
    [Fact]
    public void AddAIAgentWithFactory_NullBuilder_ThrowsArgumentNullException() =>
        Assert.Throws<ArgumentNullException>(() =>
            AgentHostingServiceCollectionExtensions.AddAIAgent(null!, "agentName", (sp, key) => new Mock<AIAgent>().Object));

    /// <summary>
    /// Verifies that AddAIAgent with factory delegate throws ArgumentNullException for null name.
    /// </summary>
    [Fact]
    public void AddAIAgentWithFactory_NullName_ThrowsArgumentNullException()
    {
        var services = new ServiceCollection();
        var exception = Assert.Throws<ArgumentNullException>(() => services.AddAIAgent(null!, (sp, key) => new Mock<AIAgent>().Object));
        Assert.Equal("name", exception.ParamName);
    }

    /// <summary>
    /// Verifies that AddAIAgent with factory delegate throws ArgumentNullException for null factory.
    /// </summary>
    [Fact]
    public void AddAIAgentWithFactory_NullFactory_ThrowsArgumentNullException()
    {
        var services = new ServiceCollection();
        var exception = Assert.Throws<ArgumentNullException>(() => services.AddAIAgent("agentName", (Func<IServiceProvider, string, AIAgent>)null!));
        Assert.Equal("createAgentDelegate", exception.ParamName);
    }

    /// <summary>
    /// Verifies that AddAIAgent with factory delegate returns the same builder instance.
    /// </summary>
    [Fact]
    public void AddAIAgentWithFactory_ValidParameters_ReturnsBuilder()
    {
        var services = new ServiceCollection();
        var mockAgent = new Mock<AIAgent>();
        var result = services.AddAIAgent("agentName", (sp, key) => mockAgent.Object);
        Assert.NotNull(result);
    }

    /// <summary>
    /// Verifies that AddAIAgent registers the agent as a keyed singleton service by default.
    /// </summary>
    [Fact]
    public void AddAIAgent_RegistersKeyedSingleton()
    {
        var services = new ServiceCollection();
        var mockAgent = new Mock<AIAgent>();
        const string AgentName = "testAgent";

        services.AddAIAgent(AgentName, (sp, key) => mockAgent.Object);

        var descriptor = services.FirstOrDefault(
            d => (d.ServiceKey as string) == AgentName &&
                 d.ServiceType == typeof(AIAgent));

        Assert.NotNull(descriptor);
        Assert.Equal(ServiceLifetime.Singleton, descriptor.Lifetime);
    }

    /// <summary>
    /// Verifies that AddAIAgent can be called multiple times with different agent names.
    /// </summary>
    [Fact]
    public void AddAIAgent_MultipleCalls_RegistersMultipleAgents()
    {
        var services = new ServiceCollection();

        services.AddAIAgent("agent1", "instructions1");
        services.AddAIAgent("agent2", "instructions2");
        services.AddAIAgent("agent3", "instructions3");

        var agentDescriptors = services
            .Where(d => d.ServiceType == typeof(AIAgent) && d.ServiceKey is string)
            .ToList();

        Assert.Equal(3, agentDescriptors.Count);
        Assert.Contains(agentDescriptors, d => (string)d.ServiceKey! == "agent1");
        Assert.Contains(agentDescriptors, d => (string)d.ServiceKey! == "agent2");
        Assert.Contains(agentDescriptors, d => (string)d.ServiceKey! == "agent3");
    }

    /// <summary>
    /// Verifies that AddAIAgent handles empty strings for name.
    /// </summary>
    [Fact]
    public void AddAIAgent_EmptyName_ThrowsArgumentException()
    {
        var services = new ServiceCollection();
        Assert.Throws<ArgumentException>(() => services.AddAIAgent("", "instructions"));
    }

    /// <summary>
    /// Verifies that AddAIAgent allows empty strings for instructions.
    /// </summary>
    [Fact]
    public void AddAIAgent_EmptyInstructions_Succeeds()
    {
        var services = new ServiceCollection();
        var result = services.AddAIAgent("agentName", "");
        Assert.NotNull(result);
    }
    /// <summary>
    /// Verifies that AddAIAgent without chat client key calls the overload with null key.
    /// </summary>
    [Fact]
    public void AddAIAgent_WithoutKey_CallsOverloadWithNullKey()
    {
        var builder = new HostApplicationBuilder();
        var result = builder.AddAIAgent("agentName", "instructions");

        // The agent should be registered (proving the method chain worked)
        var descriptor = builder.Services.FirstOrDefault(
            d => d.ServiceKey is "agentName" &&
                 d.ServiceType == typeof(AIAgent));
        Assert.NotNull(descriptor);
    }

    /// <summary>
    /// Verifies that AddAIAgent with special characters in name works correctly for valid names.
    /// </summary>
    [Theory]
    [InlineData("agent_name")] // underscore is allowed
    [InlineData("Agent123")] // alphanumeric is allowed
    [InlineData("_agent")] // can start with underscore
    [InlineData("agent-name")] // dash is allowed
    [InlineData("agent.name")] // period is allowed
    [InlineData("agent:type")] // colon is allowed
    [InlineData("my.agent_1:type-name")] // complex valid name
    public void AddAIAgent_ValidSpecialCharactersInName_Succeeds(string name)
    {
        var builder = new HostApplicationBuilder();
        var result = builder.AddAIAgent(name, "instructions");

        var descriptor = builder.Services.FirstOrDefault(
            d => (d.ServiceKey as string) == name &&
                 d.ServiceType == typeof(AIAgent));
        Assert.NotNull(descriptor);
    }

    /// <summary>
    /// Verifies that AddAIAgent registers with the specified scoped lifetime.
    /// </summary>
    [Fact]
    public void AddAIAgent_WithScopedLifetime_RegistersKeyedScoped()
    {
        // Arrange
        var services = new ServiceCollection();
        var mockAgent = new Mock<AIAgent>();
        const string AgentName = "scopedAgent";

        // Act
        var result = services.AddAIAgent(AgentName, (sp, key) => mockAgent.Object, ServiceLifetime.Scoped);

        // Assert
        var descriptor = services.FirstOrDefault(
            d => (d.ServiceKey as string) == AgentName &&
                 d.ServiceType == typeof(AIAgent));

        Assert.NotNull(descriptor);
        Assert.Equal(ServiceLifetime.Scoped, descriptor.Lifetime);
        Assert.Equal(ServiceLifetime.Scoped, result.Lifetime);
    }

    /// <summary>
    /// Verifies that AddAIAgent registers with the specified transient lifetime.
    /// </summary>
    [Fact]
    public void AddAIAgent_WithTransientLifetime_RegistersKeyedTransient()
    {
        // Arrange
        var services = new ServiceCollection();
        var mockAgent = new Mock<AIAgent>();
        const string AgentName = "transientAgent";

        // Act
        var result = services.AddAIAgent(AgentName, (sp, key) => mockAgent.Object, ServiceLifetime.Transient);

        // Assert
        var descriptor = services.FirstOrDefault(
            d => (d.ServiceKey as string) == AgentName &&
                 d.ServiceType == typeof(AIAgent));

        Assert.NotNull(descriptor);
        Assert.Equal(ServiceLifetime.Transient, descriptor.Lifetime);
        Assert.Equal(ServiceLifetime.Transient, result.Lifetime);
    }

    /// <summary>
    /// Verifies that the builder exposes the correct lifetime for default registration.
    /// </summary>
    [Fact]
    public void AddAIAgent_DefaultLifetime_BuilderExposesSingleton()
    {
        // Arrange
        var services = new ServiceCollection();
        var mockAgent = new Mock<AIAgent>();

        // Act
        var result = services.AddAIAgent("agentName", (sp, key) => mockAgent.Object);

        // Assert
        Assert.Equal(ServiceLifetime.Singleton, result.Lifetime);
    }

    /// <summary>
    /// Verifies that AddAIAgent with instructions overload respects the lifetime parameter.
    /// </summary>
    [Theory]
    [InlineData(ServiceLifetime.Singleton)]
    [InlineData(ServiceLifetime.Scoped)]
    [InlineData(ServiceLifetime.Transient)]
    public void AddAIAgent_InstructionsOverload_RespectsLifetime(ServiceLifetime lifetime)
    {
        // Arrange
        var services = new ServiceCollection();

        // Act
        var result = services.AddAIAgent("agent", "instructions", lifetime);

        // Assert
        var descriptor = services.FirstOrDefault(
            d => (d.ServiceKey as string) == "agent" &&
                 d.ServiceType == typeof(AIAgent));

        Assert.NotNull(descriptor);
        Assert.Equal(lifetime, descriptor.Lifetime);
        Assert.Equal(lifetime, result.Lifetime);
    }

    /// <summary>
    /// Verifies end-to-end that a tool invoked by an agent registered via <c>AddAIAgent</c> receives the
    /// application's <see cref="IServiceProvider"/> in its <see cref="AIFunctionArguments.Services"/>, and can
    /// therefore resolve its dependencies at invocation time.
    /// Regression test for https://github.com/microsoft/agent-framework/issues/4453.
    /// </summary>
    [Theory]
    [InlineData(AddAIAgentOverload.Instructions)]
    [InlineData(AddAIAgentOverload.ChatClientInstance)]
    [InlineData(AddAIAgentOverload.ChatClientServiceKey)]
    [InlineData(AddAIAgentOverload.DescriptionAndChatClientServiceKey)]
    public async Task AddAIAgent_ToolInvocationCanResolveServicesFromDIAsync(AddAIAgentOverload overload)
    {
        // Arrange
        var tool = new ServiceCapturingAIFunction();
        var services = new ServiceCollection();
        services.AddSingleton<IMarkerService, MarkerService>();
        RegisterAgent(services, overload).WithAITool(tool);

        var serviceProvider = services.BuildServiceProvider();
        var agent = serviceProvider.GetRequiredKeyedService<AIAgent>(AgentName);

        // Act
        var response = await agent.RunAsync("call the tool");

        // Assert
        Assert.Equal("done", response.Text);
        Assert.True(tool.WasInvoked);
        Assert.NotNull(tool.ResolvedMarkerService);
    }

    private const string AgentName = "test-agent";
    private const string ChatClientServiceKey = "test-chat-client";

    /// <summary>
    /// Identifies which <c>AddAIAgent</c> overload a test exercises.
    /// </summary>
    public enum AddAIAgentOverload
    {
        /// <summary>The overload taking only a name and instructions.</summary>
        Instructions,

        /// <summary>The overload taking an <see cref="IChatClient"/> instance.</summary>
        ChatClientInstance,

        /// <summary>The overload taking a chat client service key.</summary>
        ChatClientServiceKey,

        /// <summary>The overload taking a description and a chat client service key.</summary>
        DescriptionAndChatClientServiceKey,
    }

    private static IHostedAgentBuilder RegisterAgent(IServiceCollection services, AddAIAgentOverload overload)
    {
        switch (overload)
        {
            case AddAIAgentOverload.Instructions:
                services.AddSingleton<IChatClient>(new ToolCallingChatClient());
                return services.AddAIAgent(AgentName, "Test instructions");

            case AddAIAgentOverload.ChatClientInstance:
                return services.AddAIAgent(AgentName, "Test instructions", new ToolCallingChatClient());

            case AddAIAgentOverload.ChatClientServiceKey:
                services.AddKeyedSingleton<IChatClient>(ChatClientServiceKey, new ToolCallingChatClient());
                return services.AddAIAgent(AgentName, "Test instructions", (object?)ChatClientServiceKey);

            case AddAIAgentOverload.DescriptionAndChatClientServiceKey:
                services.AddKeyedSingleton<IChatClient>(ChatClientServiceKey, new ToolCallingChatClient());
                return services.AddAIAgent(AgentName, "Test instructions", "A test agent", ChatClientServiceKey);

            default:
                throw new ArgumentOutOfRangeException(nameof(overload));
        }
    }

    /// <summary>
    /// Marker service used to verify that the application's service provider is reachable from tool invocations.
    /// </summary>
    private interface IMarkerService;

    [System.Diagnostics.CodeAnalysis.SuppressMessage("Performance", "CA1812:Avoid uninstantiated internal classes", Justification = "Instantiated via dependency injection.")]
    private sealed class MarkerService : IMarkerService;

    /// <summary>
    /// An <see cref="AIFunction"/> that records whether it could resolve <see cref="IMarkerService"/> from the
    /// <see cref="AIFunctionArguments.Services"/> supplied at invocation time.
    /// </summary>
    private sealed class ServiceCapturingAIFunction : AIFunction
    {
        public bool WasInvoked { get; private set; }

        public IMarkerService? ResolvedMarkerService { get; private set; }

        public override string Name => "TestTool";

        public override string Description => "A test tool.";

        protected override ValueTask<object?> InvokeCoreAsync(AIFunctionArguments arguments, CancellationToken cancellationToken)
        {
            this.WasInvoked = true;
            this.ResolvedMarkerService = arguments.Services?.GetService<IMarkerService>();
            return new ValueTask<object?>("tool result");
        }
    }

    /// <summary>
    /// A chat client that requests the test tool on the first call and returns a final answer afterwards.
    /// </summary>
    private sealed class ToolCallingChatClient : IChatClient
    {
        private int _callCount;

        public Task<ChatResponse> GetResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default)
        {
            var content = Interlocked.Increment(ref this._callCount) == 1
                ? new FunctionCallContent(callId: "call-1", name: "TestTool", arguments: null)
                : (AIContent)new TextContent("done");

            return Task.FromResult(new ChatResponse(new ChatMessage(ChatRole.Assistant, [content])));
        }

        public IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default)
            => throw new NotImplementedException();

        public object? GetService(Type serviceType, object? serviceKey = null) => null;

        public void Dispose()
        {
        }
    }
}
