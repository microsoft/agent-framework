// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Threading.Tasks;
using Azure.AI.AgentServer.Responses;
using Azure.Core;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Diagnostics.HealthChecks;
using Microsoft.Extensions.Options;
using Moq;
using OpenAI.Responses;

#pragma warning disable OPENAI001 // Experimental Responses API surfaces

namespace Microsoft.Agents.AI.Foundry.Hosting.UnitTests;

public class ServiceCollectionExtensionsTests
{
    [Fact]
    public void AddFoundryResponses_MarksFeatureUsed()
    {
        // Arrange
        var services = new ServiceCollection();
        services.AddLogging();

        // Act
        services.AddFoundryResponses(Mock.Of<AIAgent>());

        // Assert
        AssertFeatureUsed(53);
    }

    [Fact]
    public void AddFoundryToolboxService_MarksFeatureUsed()
    {
        // Arrange
        var services = new ServiceCollection();

        // Act
        services.AddFoundryToolboxService(Mock.Of<TokenCredential>(), "toolbox");

        // Assert
        AssertFeatureUsed(52);
    }

    [Fact]
    public void AddFoundryToolboxService_DoesNotChangeHealthChecks()
    {
        // Arrange
        var services = new ServiceCollection();
        services.AddHealthChecks().AddCheck("custom", () => HealthCheckResult.Healthy());

        // Act
        services.AddFoundryToolboxService(Mock.Of<TokenCredential>(), "toolbox");
        using ServiceProvider provider = services.BuildServiceProvider();
        var options = provider.GetRequiredService<IOptions<HealthCheckServiceOptions>>().Value;

        // Assert
        Assert.Equal("custom", Assert.Single(options.Registrations).Name);
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

    [Fact]
    public void AddFoundryResponses_RegistersResponseHandler()
    {
        var services = new ServiceCollection();
        services.AddLogging();

        services.AddFoundryResponses(Mock.Of<AIAgent>());

        var descriptor = services.FirstOrDefault(
            d => d.ServiceType == typeof(ResponseHandler));
        Assert.NotNull(descriptor);
        Assert.NotNull(descriptor.ImplementationFactory);

        using ServiceProvider provider = services.BuildServiceProvider();
        Assert.IsType<AgentFrameworkResponseHandler>(
            provider.GetRequiredService<ResponseHandler>());
    }

    [Fact]
    public void AddFoundryResponses_UsesTheStateStoreAdapterByDefault()
    {
        // Arrange
        var services = new ServiceCollection();
        services.AddLogging();

        // Act
        services.AddFoundryResponses(Mock.Of<AIAgent>());
        using var provider = services.BuildServiceProvider();

        // Assert: the AgentServer SDK behind this adapter chooses the hosted or local backend.
        Assert.IsType<FoundryAgentSessionStore>(provider.GetRequiredService<AgentSessionStore>());
    }

    [Fact]
    public void AddFoundryResponses_CalledTwice_ThrowsAndKeepsTheFirstRegistration()
    {
        // Arrange: a container serves exactly one agent.
        var services = new ServiceCollection();
        services.AddLogging();
        services.AddFoundryResponses(Mock.Of<AIAgent>());
        int registrations = services.Count;

        // Act
        var exception = Assert.Throws<InvalidOperationException>(
            () => services.AddFoundryResponses(Mock.Of<AIAgent>()));

        // Assert
        Assert.Contains("exactly one agent", exception.Message, StringComparison.Ordinal);
        Assert.Equal(registrations, services.Count);
        Assert.Single(services, d => d.ServiceType == typeof(ResponseHandler));
    }

    [Fact]
    public void AddFoundryResponses_FactoryAfterInstance_Throws()
    {
        // Arrange
        var services = new ServiceCollection();
        services.AddFoundryResponses(Mock.Of<AIAgent>());

        // Act and assert
        Assert.Throws<InvalidOperationException>(
            () => services.AddFoundryResponses(_ => Mock.Of<AIAgent>(), ServiceLifetime.Scoped));
    }

    [Fact]
    public void AddFoundryResponses_OptionsObject_AppliesAllValues()
    {
        // Arrange
        var services = new ServiceCollection();
        services.AddLogging();
        var suppliedOptions = new FoundryResponsesServerOptions
        {
            InferenceStoredOutputAllowed = true,
            OAuthConsentInterruptedToolResult = "consent interrupted",
            ExcludeReasoningEncryptedContent = true,
            DefaultModel = "server-model",
            DefaultFetchHistoryCount = 42,
            ResilientBackground = true,
            SteerableConversations = true,
        };

        // Act
        services.AddFoundryResponses(Mock.Of<AIAgent>(), options: suppliedOptions);
        using ServiceProvider provider = services.BuildServiceProvider();
        FoundryResponsesServerOptions registeredOptions =
            provider.GetRequiredService<IOptions<FoundryResponsesServerOptions>>().Value;

        // Assert
        Assert.True(registeredOptions.InferenceStoredOutputAllowed);
        Assert.Equal("consent interrupted", registeredOptions.OAuthConsentInterruptedToolResult);
        Assert.True(registeredOptions.ExcludeReasoningEncryptedContent);
        Assert.Equal("server-model", registeredOptions.DefaultModel);
        Assert.Equal(42, registeredOptions.DefaultFetchHistoryCount);
        Assert.True(registeredOptions.ResilientBackground);
        Assert.True(registeredOptions.SteerableConversations);

        ResponsesServerOptions serverOptions =
            provider.GetRequiredService<IOptions<ResponsesServerOptions>>().Value;
        Assert.Equal("server-model", serverOptions.DefaultModel);
        Assert.Equal(42, serverOptions.DefaultFetchHistoryCount);
        Assert.True(serverOptions.ResilientBackground);
        Assert.True(serverOptions.SteerableConversations);
    }

    [Fact]
    public void AddFoundryResponses_Factory_AppliesOptions()
    {
        // Arrange
        var services = new ServiceCollection();
        services.AddLogging();

        // Act
        services.AddFoundryResponses(
            _ => Mock.Of<AIAgent>(),
            ServiceLifetime.Scoped,
            new FoundryResponsesServerOptions { InferenceStoredOutputAllowed = true });
        using ServiceProvider provider = services.BuildServiceProvider();

        // Assert
        Assert.True(provider.GetRequiredService<IOptions<FoundryResponsesServerOptions>>().Value.InferenceStoredOutputAllowed);
    }

    [Fact]
    public void AddFoundryResponses_NullServices_ThrowsArgumentNullException()
    {
        Assert.Throws<ArgumentNullException>(
            () => ServiceCollectionExtensions.AddFoundryResponses(null!, Mock.Of<AIAgent>()));
        Assert.Throws<ArgumentNullException>(
            () => ServiceCollectionExtensions.AddFoundryResponses(null!, _ => Mock.Of<AIAgent>()));
    }

    [Fact]
    public void AddFoundryResponses_WithAgent_RegistersTheHandlerButNotTheAgent()
    {
        // Arrange
        var services = new ServiceCollection();
        services.AddLogging();
        var agent = Mock.Of<AIAgent>();

        // Act
        services.AddFoundryResponses(agent);

        // Assert: hosting serves the agent without putting it in DI.
        Assert.Contains(services, d => d.ServiceType == typeof(ResponseHandler));
        Assert.DoesNotContain(services, d => d.ServiceType == typeof(AIAgent));
        using ServiceProvider provider = services.BuildServiceProvider();
        Assert.Null(provider.GetService<AIAgent>());
        Assert.Empty(provider.GetKeyedServices<AIAgent>(KeyedService.AnyKey));
    }

    [Fact]
    public void AddFoundryResponses_WithNullAgent_ThrowsArgumentNullException()
    {
        var services = new ServiceCollection();
        // Cast to bind the agent overload: a null literal also converts to the factory overload's delegate.
        Assert.Throws<ArgumentNullException>(
            () => services.AddFoundryResponses((AIAgent)null!));
        Assert.Empty(services);
    }

    [Fact]
    public void AddFoundryResponses_WithNullFactory_ThrowsArgumentNullException()
    {
        var services = new ServiceCollection();
        Assert.Throws<ArgumentNullException>(
            () => services.AddFoundryResponses((Func<IServiceProvider, AIAgent>)null!));
        Assert.Empty(services);
    }

    [Fact]
    public void AddFoundryResponses_UnsupportedLifetime_ThrowsArgumentOutOfRangeException()
    {
        var services = new ServiceCollection();
        Assert.Throws<ArgumentOutOfRangeException>(
            () => services.AddFoundryResponses(_ => Mock.Of<AIAgent>(), (ServiceLifetime)42));
        Assert.Empty(services);
    }

    [Fact]
    public async Task AddFoundryToolboxService_OptionsObject_CopiesOptionalBehaviorAsync()
    {
        // Arrange
        var services = new ServiceCollection();
        var suppliedOptions = new FoundryToolboxServiceOptions
        {
            TokenScope = "https://example.test/.default",
            AllowedOAuthConsentOrigins =
                new HashSet<Uri> { new("https://login.example.test") },
        };

        // Act
        services.AddFoundryToolboxService(
            Mock.Of<TokenCredential>(),
            suppliedOptions,
            "first-toolbox",
            " ",
            "second-toolbox");
        suppliedOptions.AllowedOAuthConsentOrigins.Clear();
        suppliedOptions.AllowedOAuthConsentOrigins.Add(new Uri("https://mutated.example.test"));
        await using ServiceProvider provider = services.BuildServiceProvider();
        FoundryToolboxService service = provider.GetRequiredService<FoundryToolboxService>();
        FieldInfo optionsField = typeof(FoundryToolboxService).GetField(
            "_options",
            BindingFlags.Instance | BindingFlags.NonPublic)
            ?? throw new InvalidOperationException("Foundry toolbox options field not found.");
        FoundryToolboxServiceOptions registeredOptions =
            Assert.IsType<FoundryToolboxServiceOptions>(optionsField.GetValue(service));

        // Assert
        Assert.Equal("https://example.test/.default", registeredOptions.TokenScope);
        ISet<Uri> allowedOrigins = Assert.IsAssignableFrom<ISet<Uri>>(registeredOptions.AllowedOAuthConsentOrigins);
        Assert.Contains(new Uri("https://login.example.test"), allowedOrigins);
        Assert.DoesNotContain(new Uri("https://mutated.example.test"), allowedOrigins);
        Assert.Equal(["first-toolbox", "second-toolbox"], registeredOptions.ToolboxNames);
    }

    [Fact]
    public void ApplyOpenTelemetry_NonInstrumentedAgent_WrapsWithOpenTelemetryAgent()
    {
        var mockAgent = new Mock<AIAgent>();

        var result = ServiceCollectionExtensions.ApplyOpenTelemetry(mockAgent.Object);

        Assert.NotNull(result.GetService<OpenTelemetryAgent>());
    }

    [Fact]
    public void ApplyOpenTelemetry_AlreadyInstrumentedAgent_ReturnsSameReference()
    {
        var mockAgent = new Mock<AIAgent>();
        var instrumented = mockAgent.Object.AsBuilder()
            .UseOpenTelemetry()
            .Build();

        var result = ServiceCollectionExtensions.ApplyOpenTelemetry(instrumented);

        Assert.Same(instrumented, result);
    }

    [Fact]
    public void TryApplyUserAgent_AgentWithoutChatClient_NoOp()
    {
        // Arrange: agent.GetService<IChatClient>() returns null.
        var mockAgent = new Mock<AIAgent>();

        // Act
        var result = ServiceCollectionExtensions.TryApplyUserAgent(mockAgent.Object);

        // Assert
        Assert.Same(mockAgent.Object, result);
    }

    [Fact]
    public void TryApplyUserAgent_AgentWithNonMeaiChatClient_NoOp()
    {
        // Arrange: chat client that does not return MEAI's OpenAIResponsesChatClient via GetService.
        var mockChatClient = new Mock<IChatClient>();
        mockChatClient.Setup(c => c.GetService(It.IsAny<Type>(), It.IsAny<object?>())).Returns(null!);

        var mockAgent = new Mock<AIAgent>();
        mockAgent.Setup(a => a.GetService(typeof(IChatClient), It.IsAny<object?>())).Returns(mockChatClient.Object);

        // Act
        var result = ServiceCollectionExtensions.TryApplyUserAgent(mockAgent.Object);

        // Assert
        Assert.Same(mockAgent.Object, result);
    }

    [Fact]
    public void MeaiOpenAIResponsesChatClient_TypeFullName_ReflectionGuard()
    {
        // Guards the polyfill's reflection target type-name.
        var meaiType = typeof(MicrosoftExtensionsAIResponsesExtensions).Assembly
            .GetType("Microsoft.Extensions.AI.OpenAIResponsesChatClient");
        Assert.NotNull(meaiType);
        Assert.True(typeof(IChatClient).IsAssignableFrom(meaiType!),
            $"Expected MEAI {meaiType!.FullName} to implement IChatClient.");
    }
}
