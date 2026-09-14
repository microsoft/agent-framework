// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;

namespace Microsoft.Agents.AI.Hosting.OpenAI.UnitTests;

/// <summary>
/// Tests permissive client function mapping across agent implementations.
/// </summary>
public sealed class OpenAIResponsesAgentCompatibilityTests
{
    [Theory]
    [InlineData(false, "direct")]
    [InlineData(true, "direct")]
    [InlineData(false, "wrapped")]
    [InlineData(true, "wrapped")]
    [InlineData(false, "opaque")]
    [InlineData(true, "opaque")]
    public async Task DefaultMapping_ForwardsFunctionsWithoutRequiringDiscoverableChatClientAgentAsync(bool resolveByName, string agentKind)
    {
        // Arrange
        using var chatClient = new TestHelpers.SimpleMockChatClient();
        ChatClientAgent inner = chatClient.AsAIAgent(name: "test-agent");
        AIAgent agent = agentKind switch
        {
            "direct" => inner,
            "wrapped" => new TestDelegatingAgent(inner),
            _ => new OpaqueAgent(inner)
        };
        await using WebApplication app = await CreateServerAsync(agent, resolveByName);
        using HttpClient client = app.GetTestClient();
        using var content = CreateRequest(withTools: true);

        // Act
        using HttpResponseMessage response = await client.PostAsync(new Uri("/v1/responses", UriKind.Relative), content);

        // Assert
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.IsAssignableFrom<AIFunctionDeclaration>(Assert.Single(chatClient.LastChatOptions!.Tools!));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task DefaultMapping_AgentIgnoringChatOptions_CanRespondAsync(bool resolveByName)
    {
        // Arrange
        var agent = new NonChatAgent();
        await using WebApplication app = await CreateServerAsync(agent, resolveByName);
        using HttpClient client = app.GetTestClient();
        using var content = CreateRequest(withTools: true);

        // Act
        using HttpResponseMessage response = await client.PostAsync(new Uri("/v1/responses", UriKind.Relative), content);

        // Assert
        Assert.Null(agent.GetService<ChatClientAgent>());
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.Contains("Response without function support.", await response.Content.ReadAsStringAsync());
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task DefaultMapping_WithoutClientFunctions_DoesNotRequireChatClientAgentAsync(bool resolveByName)
    {
        // Arrange
        using var chatClient = new TestHelpers.SimpleMockChatClient();
        AIAgent agent = new OpaqueAgent(chatClient.AsAIAgent(name: "test-agent"));
        await using WebApplication app = await CreateServerAsync(agent, resolveByName);
        using HttpClient client = app.GetTestClient();
        using var content = CreateRequest(withTools: false);

        // Act
        using HttpResponseMessage response = await client.PostAsync(new Uri("/v1/responses", UriKind.Relative), content);

        // Assert
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task CustomMapping_DoesNotRequireChatClientAgentAsync(bool resolveByName)
    {
        // Arrange
        using var chatClient = new TestHelpers.SimpleMockChatClient();
        AIAgent agent = new OpaqueAgent(chatClient.AsAIAgent(name: "test-agent"));
        AIFunction tool = AIFunctionFactory.Create(() => "server", "server_function");
        await using WebApplication app = await CreateServerAsync(
            agent,
            resolveByName,
            _ => new ChatClientAgentRunOptions(new ChatOptions { Tools = [tool] }));
        using HttpClient client = app.GetTestClient();
        using var content = CreateRequest(withTools: true);

        // Act
        using HttpResponseMessage response = await client.PostAsync(new Uri("/v1/responses", UriKind.Relative), content);

        // Assert
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.Same(tool, Assert.Single(chatClient.LastChatOptions!.Tools!));
    }

    private static async Task<WebApplication> CreateServerAsync(
        AIAgent agent,
        bool resolveByName,
        Func<OpenAIResponseRequestInfo, AgentRunOptions?>? factory = null)
    {
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        builder.WebHost.UseTestServer();
        builder.AddOpenAIResponses();
        builder.Services.AddKeyedSingleton("test-agent", agent);
#pragma warning disable MAAI001
        var mapOptions = new OpenAIResponsesMapOptions { DangerouslyAllowClientFunctionTools = true };
#pragma warning restore MAAI001
        if (factory is not null)
        {
            mapOptions.RunOptionsFactory = factory;
        }

        builder.Services.AddSingleton(mapOptions);
        WebApplication app = builder.Build();
        if (resolveByName)
        {
            app.MapOpenAIResponses();
        }
        else
        {
            app.MapOpenAIResponses(agent, "/v1/responses", mapOptions);
        }

        await app.StartAsync();
        return app;
    }

    private static StringContent CreateRequest(bool withTools) => new(
        withTools
            ? """{"agent":{"name":"test-agent"},"input":"hello","tools":[{"type":"function","name":"client_function"}]}"""
            : """{"agent":{"name":"test-agent"},"input":"hello"}""",
        Encoding.UTF8,
        "application/json");

    private sealed class TestDelegatingAgent(AIAgent innerAgent) : DelegatingAIAgent(innerAgent);

    private sealed class OpaqueAgent(AIAgent innerAgent) : DelegatingAIAgent(innerAgent)
    {
        public override object? GetService(Type serviceType, object? serviceKey = null) =>
            serviceType == typeof(ChatClientAgent) ? null : base.GetService(serviceType, serviceKey);
    }

    private sealed class NonChatAgent : AIAgent
    {
        public override string Name => "test-agent";

        protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default) =>
            new(new TestSession());

        protected override ValueTask<JsonElement> SerializeSessionCoreAsync(
            AgentSession session, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default) =>
            throw new NotSupportedException();

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(
            JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default) =>
            throw new NotSupportedException();

        protected override Task<AgentResponse> RunCoreAsync(
            IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null,
            CancellationToken cancellationToken = default) =>
            Task.FromResult(new AgentResponse(new ChatMessage(ChatRole.Assistant, "Response without function support.")));

        protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
            IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null,
            [System.Runtime.CompilerServices.EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            await Task.CompletedTask;
            yield return new AgentResponseUpdate(ChatRole.Assistant, "Response without function support.");
        }

        private sealed class TestSession : AgentSession;
    }
}
