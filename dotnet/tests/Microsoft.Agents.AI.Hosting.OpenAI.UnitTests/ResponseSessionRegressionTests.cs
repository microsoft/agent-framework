// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Runtime.CompilerServices;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Routing;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Moq;

namespace Microsoft.Agents.AI.Hosting.OpenAI.UnitTests;

/// <summary>
/// Regression tests for session lifetime and ordering across Responses API requests.
/// </summary>
public sealed class ResponseSessionRegressionTests
{
    private const string AgentName = "session-regression-agent";
    private const string ToolName = "get_weather";

    private static readonly TimeSpan s_timeout = TimeSpan.FromSeconds(10);

    [Fact]
    public async Task ApprovalContinuation_TransientAgent_UsesStableRegistrationIdentityAsync()
    {
        // Arrange
        int modelCalls = 0;
        int toolCalls = 0;
        AIFunction function = new ApprovalRequiredAIFunction(AIFunctionFactory.Create(
            () =>
            {
                Interlocked.Increment(ref toolCalls);
                return "Sunny";
            },
            ToolName));
        Mock<IChatClient> chatClient = CreateApprovalChatClient(() => Interlocked.Increment(ref modelCalls));

        WebApplicationBuilder builder = CreateBuilder();
        builder.AddAIAgent(
                AgentName,
                (_, name) => new ChatClientAgent(chatClient.Object, name: name, tools: [function]),
                ServiceLifetime.Transient)
            .WithInMemorySessionStore(withIsolation: false);
        builder.AddOpenAIResponses();

        await using WebApplication app = builder.Build();
        app.MapOpenAIResponses();
        await app.StartAsync();
        using HttpClient client = app.GetTestClient();

        (string responseId, JsonElement approvalEvent) = await CreatePendingApprovalAsync(
            client,
            "/v1/responses",
            includeAgentName: true);
        using StringContent approvalContent = JsonContent(CreateApprovalResponseJson(
            responseId,
            approvalEvent,
            includeAgentName: true));

        // Act
        using HttpResponseMessage response = await client.PostAsync(
            new Uri("/v1/responses", UriKind.Relative),
            approvalContent);
        string responseBody = await response.Content.ReadAsStringAsync();

        // Assert
        Assert.True(response.IsSuccessStatusCode, responseBody);
        Assert.Equal(1, toolCalls);
        Assert.Equal(2, modelCalls);
    }

    [Fact]
    public async Task ApprovalContinuation_AgentSelectorReturningNewInstances_UsesStableAgentNameAsync()
    {
        // Arrange
        int modelCalls = 0;
        int toolCalls = 0;
        int selectedAgents = 0;
        AIFunction function = new ApprovalRequiredAIFunction(AIFunctionFactory.Create(
            () =>
            {
                Interlocked.Increment(ref toolCalls);
                return "Sunny";
            },
            ToolName));
        Mock<IChatClient> chatClient = CreateApprovalChatClient(() => Interlocked.Increment(ref modelCalls));

        WebApplicationBuilder builder = CreateBuilder(validateScopes: true);
        builder.Services.AddKeyedSingleton<AgentSessionStore>(AgentName, new InMemoryAgentSessionStore());
        builder.AddOpenAIResponses();

        await using WebApplication app = builder.Build();
        app.MapOpenAIResponses("/agents/{agentId}/v1/responses", context =>
        {
            Interlocked.Increment(ref selectedAgents);
            return context.GetRouteValue("agentId") as string == AgentName
                ? new ChatClientAgent(chatClient.Object, name: AgentName, tools: [function])
                : null;
        });
        await app.StartAsync();
        using HttpClient client = app.GetTestClient();
        string path = $"/agents/{AgentName}/v1/responses";

        (string responseId, JsonElement approvalEvent) = await CreatePendingApprovalAsync(
            client,
            path,
            includeAgentName: false);
        using StringContent approvalContent = JsonContent(CreateApprovalResponseJson(
            responseId,
            approvalEvent,
            includeAgentName: false));

        // Act
        using HttpResponseMessage response = await client.PostAsync(
            new Uri(path, UriKind.Relative),
            approvalContent);
        string responseBody = await response.Content.ReadAsStringAsync();

        // Assert
        Assert.True(response.IsSuccessStatusCode, responseBody);
        Assert.Equal(2, selectedAgents);
        Assert.Equal(1, toolCalls);
        Assert.Equal(2, modelCalls);
    }

    [Fact]
    public async Task AgentSelector_ReturningNull_ReturnsNotFoundAsync()
    {
        // Arrange
        WebApplicationBuilder builder = CreateBuilder();
        builder.AddOpenAIResponses();

        await using WebApplication app = builder.Build();
        app.MapOpenAIResponses("/agents/{agentId}/v1/responses", _ => null);
        await app.StartAsync();
        using HttpClient client = app.GetTestClient();

        // Act
        using HttpResponseMessage response = await PostJsonAsync(
            client,
            "/agents/unknown/v1/responses",
            """{"input":"hello"}""");
        string responseBody = await response.Content.ReadAsStringAsync();

        // Assert
        Assert.Equal(System.Net.HttpStatusCode.NotFound, response.StatusCode);
        Assert.Contains("agent_not_found", responseBody, StringComparison.Ordinal);
    }

    [Theory]
    [InlineData("GET", "/agents/unknown/v1/responses/resp_1")]
    [InlineData("POST", "/agents/unknown/v1/responses/resp_1/cancel")]
    [InlineData("DELETE", "/agents/unknown/v1/responses/resp_1")]
    [InlineData("GET", "/agents/unknown/v1/responses/resp_1/input_items")]
    public async Task AgentSelector_ReturningNull_ReturnsNotFoundForStoredResponseOperationsAsync(string method, string path)
    {
        // Arrange
        int selections = 0;
        WebApplicationBuilder builder = CreateBuilder();
        builder.AddOpenAIResponses();

        await using WebApplication app = builder.Build();
        app.MapOpenAIResponses("/agents/{agentId}/v1/responses", _ =>
        {
            Interlocked.Increment(ref selections);
            return null;
        });
        await app.StartAsync();
        using HttpClient client = app.GetTestClient();

        // Act
        using HttpRequestMessage request = new(new HttpMethod(method), new Uri(path, UriKind.Relative));
        using HttpResponseMessage response = await client.SendAsync(request);
        string responseBody = await response.Content.ReadAsStringAsync();

        // Assert
        Assert.Equal(System.Net.HttpStatusCode.NotFound, response.StatusCode);
        Assert.Contains("agent_not_found", responseBody, StringComparison.Ordinal);
        Assert.Equal(1, selections);
    }

    [Fact]
    public async Task AgentSelector_BindsStoredResponsesToSelectedAgentAsync()
    {
        // Arrange
        Dictionary<string, AIAgent> agents = new(StringComparer.Ordinal)
        {
            ["alpha"] = new ChatClientAgent(new TestHelpers.SimpleMockChatClient("Alpha response"), name: "alpha"),
            ["beta"] = new ChatClientAgent(new TestHelpers.SimpleMockChatClient("Beta response"), name: "beta"),
        };
        WebApplicationBuilder builder = CreateBuilder();
        builder.AddOpenAIResponses();

        await using WebApplication app = builder.Build();
        app.MapOpenAIResponses(
            "/agents/{agentId}/v1/responses",
            context => context.GetRouteValue("agentId") is string agentId ? agents.GetValueOrDefault(agentId) : null);
        await app.StartAsync();
        using HttpClient client = app.GetTestClient();

        using HttpResponseMessage createResponse = await PostJsonAsync(
            client,
            "/agents/alpha/v1/responses",
            """{"input":"hello"}""");
        string createBody = await createResponse.Content.ReadAsStringAsync();
        Assert.True(createResponse.IsSuccessStatusCode, createBody);
        string responseId = JsonDocument.Parse(createBody).RootElement.GetProperty("id").GetString()!;

        // Act
        using HttpResponseMessage otherAgentGet = await client.GetAsync(new Uri($"/agents/beta/v1/responses/{responseId}", UriKind.Relative));
        using HttpResponseMessage otherAgentInputItems = await client.GetAsync(new Uri($"/agents/beta/v1/responses/{responseId}/input_items", UriKind.Relative));
        using HttpResponseMessage otherAgentDelete = await client.DeleteAsync(new Uri($"/agents/beta/v1/responses/{responseId}", UriKind.Relative));
        using HttpResponseMessage ownerGet = await client.GetAsync(new Uri($"/agents/alpha/v1/responses/{responseId}", UriKind.Relative));
        string ownerBody = await ownerGet.Content.ReadAsStringAsync();

        // Assert
        Assert.Equal(System.Net.HttpStatusCode.NotFound, otherAgentGet.StatusCode);
        Assert.Equal(System.Net.HttpStatusCode.NotFound, otherAgentInputItems.StatusCode);
        Assert.Equal(System.Net.HttpStatusCode.NotFound, otherAgentDelete.StatusCode);
        Assert.True(ownerGet.IsSuccessStatusCode, ownerBody);
        Assert.Contains("Alpha response", ownerBody, StringComparison.Ordinal);
    }

    [Fact]
    public async Task AgentSelector_ResolvesScopedAgentFromRequestServicesAsync()
    {
        // Arrange
        WebApplicationBuilder builder = CreateBuilder(validateScopes: true);
        builder.AddAIAgent(
            AgentName,
            (_, name) => new ChatClientAgent(new TestHelpers.SimpleMockChatClient("Scoped response"), name: name),
            ServiceLifetime.Scoped);
        builder.AddOpenAIResponses();

        await using WebApplication app = builder.Build();
        app.MapOpenAIResponses(
            "/agents/{agentId}/v1/responses",
            context => context.RequestServices.GetKeyedService<AIAgent>(context.GetRouteValue("agentId")));
        await app.StartAsync();
        using HttpClient client = app.GetTestClient();

        // Act
        using HttpResponseMessage response = await PostJsonAsync(
            client,
            $"/agents/{AgentName}/v1/responses",
            """{"input":"hello"}""");
        string responseBody = await response.Content.ReadAsStringAsync();

        // Assert
        Assert.True(response.IsSuccessStatusCode, responseBody);
        Assert.Contains("Scoped response", responseBody, StringComparison.Ordinal);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task ScopedSessionStore_IsResolvedFromExecutionScopeAsync(bool resolveAgent)
    {
        // Arrange
        WebApplicationBuilder builder = CreateBuilder(validateScopes: true);
        AIAgent agent = new ChatClientAgent(new TestHelpers.SimpleMockChatClient(), name: AgentName);
        builder.AddAIAgent(AgentName, (_, _) => agent)
            .WithSessionStore(
                (_, _) => new InMemoryAgentSessionStore(),
                ServiceLifetime.Scoped,
                withIsolation: false);
        builder.AddOpenAIResponses();

        await using WebApplication app = builder.Build();
        if (resolveAgent)
        {
            app.MapOpenAIResponses();
        }
        else
        {
            app.MapOpenAIResponses(agent);
        }
        await app.StartAsync();
        using HttpClient client = app.GetTestClient();
        string path = resolveAgent ? "/v1/responses" : $"/{AgentName}/v1/responses";
        using StringContent content = JsonContent($$"""
            {
              "agent": { "name": "{{AgentName}}" },
              "input": "hello"
            }
            """);

        // Act
        using HttpResponseMessage response = await client.PostAsync(
            new Uri(path, UriKind.Relative),
            content);

        // Assert
        response.EnsureSuccessStatusCode();
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task ScopedAgent_IsResolvedFromExecutionScopeAsync(bool resolveAgent)
    {
        // Arrange
        WebApplicationBuilder builder = CreateBuilder(validateScopes: true);
        IHostedAgentBuilder agentBuilder = builder.AddAIAgent(
            AgentName,
            (_, name) => new ChatClientAgent(new TestHelpers.SimpleMockChatClient(), name: name),
            ServiceLifetime.Scoped);
        builder.AddOpenAIResponses();

        await using WebApplication app = builder.Build();
        if (resolveAgent)
        {
            app.MapOpenAIResponses();
        }
        else
        {
            app.MapOpenAIResponses(agentBuilder);
        }
        await app.StartAsync();
        using HttpClient client = app.GetTestClient();
        string path = resolveAgent ? "/v1/responses" : $"/{AgentName}/v1/responses";
        using StringContent content = JsonContent($$"""
            {
              "agent": { "name": "{{AgentName}}" },
              "input": "hello"
            }
            """);

        // Act
        using HttpResponseMessage response = await client.PostAsync(
            new Uri(path, UriKind.Relative),
            content);

        // Assert
        response.EnsureSuccessStatusCode();
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task BackgroundExecution_KeepsScopedSessionStoreAliveThroughPersistenceAsync(bool resolveAgent)
    {
        // Arrange
        var agent = new PausingApprovalAgent();
        var storeTracker = new ScopedSessionStoreTracker();
        WebApplicationBuilder builder = CreateBuilder(validateScopes: true);
        builder.AddAIAgent(AgentName, (_, _) => agent)
            .WithSessionStore(
                (_, _) => storeTracker.CreateStore(),
                ServiceLifetime.Scoped,
                withIsolation: false);
        builder.AddOpenAIResponses();

        await using WebApplication app = builder.Build();
        if (resolveAgent)
        {
            app.MapOpenAIResponses();
        }
        else
        {
            app.MapOpenAIResponses(agent);
        }
        await app.StartAsync();
        using HttpClient client = app.GetTestClient();
        string path = resolveAgent ? "/v1/responses" : $"/{AgentName}/v1/responses";
        string requestJson = resolveAgent
            ? $$"""
                {
                  "agent": { "name": "{{AgentName}}" },
                  "input": "hello",
                  "background": true
                }
                """
            : """
                {
                  "input": "hello",
                  "background": true
                }
                """;
        using StringContent content = JsonContent(requestJson);

        // Act
        using HttpResponseMessage response = await client.PostAsync(
            new Uri(path, UriKind.Relative),
            content);
        string responseBody = await response.Content.ReadAsStringAsync();
        response.EnsureSuccessStatusCode();
        using JsonDocument responseDocument = JsonDocument.Parse(responseBody);
        string responseId = Assert.IsType<string>(
            responseDocument.RootElement.GetProperty("id").GetString());
        TrackingSessionStore executionStore =
            await storeTracker.ExecutionStoreCreated.Task.WaitAsync(TimeSpan.FromSeconds(5));

        // Assert
        try
        {
            Assert.False(executionStore.IsDisposed);
            agent.ReleaseInitialRun();
            await WaitForResponseCompletionAsync(client, path, responseId);
            await executionStore.Disposed.Task.WaitAsync(TimeSpan.FromSeconds(5));
            Assert.Equal(1, executionStore.SaveCount);
        }
        finally
        {
            agent.ReleaseInitialRun();
        }
    }

    [Fact]
    public async Task StreamingApproval_RequiresTerminalEventBeforeContinuationAsync()
    {
        // Arrange
        var agent = new PausingApprovalAgent();
        WebApplicationBuilder builder = CreateBuilder();
        builder.AddAIAgent(AgentName, (_, _) => agent)
            .WithInMemorySessionStore(withIsolation: false);
        builder.AddOpenAIResponses();

        await using WebApplication app = builder.Build();
        app.MapOpenAIResponses(agent);
        await app.StartAsync();
        using HttpClient client = app.GetTestClient();
        var initialRequest = new HttpRequestMessage(HttpMethod.Post, $"/{AgentName}/v1/responses")
        {
            Content = JsonContent("""{"input":"hello","stream":true}""")
        };
        using HttpResponseMessage initialResponse = await client.SendAsync(
            initialRequest,
            HttpCompletionOption.ResponseHeadersRead);
        initialResponse.EnsureSuccessStatusCode();
        await using Stream initialStream = await initialResponse.Content.ReadAsStreamAsync();
        using var reader = new StreamReader(initialStream);
        (string responseId, JsonElement approvalEvent) = await ReadApprovalEventAsync(reader);
        string approvalJson = CreateApprovalResponseJson(
            responseId,
            approvalEvent,
            includeAgentName: false);

        // Act
        try
        {
            using HttpResponseMessage prematureResponse = await PostJsonAsync(
                client,
                $"/{AgentName}/v1/responses",
                approvalJson).WaitAsync(TimeSpan.FromSeconds(5));
            string prematureBody = await prematureResponse.Content.ReadAsStringAsync();

            // Assert
            Assert.Equal(System.Net.HttpStatusCode.BadRequest, prematureResponse.StatusCode);
            Assert.Contains("does not match a pending approval request", prematureBody, StringComparison.Ordinal);

            // Act
            agent.ReleaseInitialRun();
            string remainingEvents = await reader.ReadToEndAsync().WaitAsync(TimeSpan.FromSeconds(5));
            Assert.Contains("response.completed", remainingEvents, StringComparison.Ordinal);
            using HttpResponseMessage approvalResponse = await PostJsonAsync(
                client,
                $"/{AgentName}/v1/responses",
                approvalJson).WaitAsync(TimeSpan.FromSeconds(5));
            string approvalBody = await approvalResponse.Content.ReadAsStringAsync();

            // Assert
            Assert.True(approvalResponse.IsSuccessStatusCode, approvalBody);
        }
        finally
        {
            agent.ReleaseInitialRun();
        }
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task AgentSelector_ResolvesSessionStoreFromRequestServicesAsync(bool stream)
    {
        // Arrange
        TenantObservations observations = new();
        WebApplicationBuilder builder = CreateBuilder(validateScopes: true);
        builder.Services.AddScoped<TenantState>();
        builder.Services.AddKeyedScoped<AgentSessionStore>(
            TenantAgent.AgentName,
            (services, _) => new TenantSessionStore(services.GetRequiredService<TenantState>(), observations));
        builder.AddOpenAIResponses();

        await using WebApplication app = builder.Build();
        app.Use((context, next) =>
        {
            context.RequestServices.GetRequiredService<TenantState>().Tenant = context.Request.Headers["X-Tenant"].ToString();
            return next(context);
        });
        app.MapOpenAIResponses(
            "/v1/responses",
            context => new TenantAgent(context.RequestServices.GetRequiredService<TenantState>(), observations));
        await app.StartAsync();
        using HttpClient client = app.GetTestClient();
        client.DefaultRequestHeaders.Add("X-Tenant", "contoso");

        // Act
        using HttpResponseMessage response = await PostJsonAsync(
            client,
            "/v1/responses",
            $$"""{"input":"hello","stream":{{(stream ? "true" : "false")}}}""");
        string responseBody = await response.Content.ReadAsStringAsync();

        // Assert
        Assert.True(response.IsSuccessStatusCode, responseBody);
        TenantState agentState = Assert.Single(observations.AgentStates);
        Assert.Equal("contoso", agentState.Tenant);
        Assert.NotEmpty(observations.StoreStates);
        Assert.All(observations.StoreStates, storeState => Assert.Same(agentState, storeState));
        Assert.Equal(["contoso", "contoso"], observations.StoreOperationTenants);
    }

    [Fact]
    public async Task AgentSelector_BackgroundResponse_ResolvesSessionStoreFromOwnScopeAsync()
    {
        // Arrange
        TenantObservations observations = new();
        WebApplicationBuilder builder = CreateBuilder(validateScopes: true);
        builder.Services.AddScoped<TenantState>();
        builder.Services.AddKeyedScoped<AgentSessionStore>(
            TenantAgent.AgentName,
            (services, _) => new TenantSessionStore(services.GetRequiredService<TenantState>(), observations));
        builder.AddOpenAIResponses();

        await using WebApplication app = builder.Build();
        app.MapOpenAIResponses(
            "/v1/responses",
            context => new TenantAgent(context.RequestServices.GetRequiredService<TenantState>(), observations));
        await app.StartAsync();
        using HttpClient client = app.GetTestClient();

        // Act
        using HttpResponseMessage response = await PostJsonAsync(client, "/v1/responses", """{"input":"hello","background":true}""");
        string responseBody = await response.Content.ReadAsStringAsync();
        Assert.True(response.IsSuccessStatusCode, responseBody);
        using JsonDocument document = JsonDocument.Parse(responseBody);
        await WaitForResponseCompletionAsync(client, "/v1/responses", document.RootElement.GetProperty("id").GetString()!);

        // Assert
        // The selector also runs for the polling requests, so the first selection is the one that created the response.
        TenantState agentState = observations.AgentStates[0];
        TenantState executionStoreState = observations.StoreStates[^1];
        Assert.DoesNotContain(executionStoreState, observations.AgentStates);
        Assert.NotSame(agentState, executionStoreState);
        Assert.Equal(2, observations.StoreOperationTenants.Count);
    }

    [Fact]
    public async Task AgentSelector_StreamingDisconnect_KeepsRequestServicesUntilRunCompletesAsync()
    {
        // Arrange
        RequestBoundRunProbe probe = new();
        await using WebApplication app = await StartRequestBoundAppAsync(probe);
        using HttpClient client = app.GetTestClient();
        using HttpRequestMessage request = new(HttpMethod.Post, new Uri("/v1/responses", UriKind.Relative))
        {
            Content = JsonContent("""{"input":"hello","stream":true}""")
        };

        // Act
#pragma warning disable CA2025 // The request is awaited below, before the request message is disposed.
        Task<HttpResponseMessage> sending = client.SendAsync(request, HttpCompletionOption.ResponseHeadersRead);
#pragma warning restore CA2025
        await probe.AgentStarted.Task.WaitAsync(s_timeout);
        HttpResponseMessage response = await sending;

        // Disposing the response before reading it to the end aborts the request on the server, like a client disconnect.
        response.Dispose();
        bool requestCompletedBeforeRun = await CompletesWithinAsync(probe.RequestCompleted.Task, TimeSpan.FromMilliseconds(500));
        probe.ReleaseAgent.SetResult();
        await probe.SessionSaved.Task.WaitAsync(s_timeout);
        await probe.RequestCompleted.Task.WaitAsync(s_timeout);

        // Assert
        Assert.False(requestCompletedBeforeRun);
        Assert.False(probe.DependencyDisposedWhenRunFinished);
        Assert.False(probe.StoreDisposedWhenSessionSaved);
    }

    [Fact]
    public async Task AgentSelector_NonStreamingDisconnect_KeepsRequestServicesUntilCanceledRunCompletesAsync()
    {
        // Arrange
        RequestBoundRunProbe probe = new() { CleanupDelay = TimeSpan.FromMilliseconds(300) };
        await using WebApplication app = await StartRequestBoundAppAsync(probe);
        using HttpClient client = app.GetTestClient();
        using CancellationTokenSource disconnect = new();

        // Act
#pragma warning disable CA2025 // The request is awaited below, before the token source is disposed.
        Task<HttpResponseMessage> sending = PostJsonAsync(client, "/v1/responses", """{"input":"hello"}""", disconnect.Token);
#pragma warning restore CA2025
        await probe.AgentStarted.Task.WaitAsync(s_timeout);
        disconnect.Cancel();
        bool requestCanceled = false;
        try
        {
            (await sending).Dispose();
        }
        catch (OperationCanceledException)
        {
            requestCanceled = true;
        }

        await probe.RunFinished.Task.WaitAsync(s_timeout);
        await probe.RequestCompleted.Task.WaitAsync(s_timeout);

        // Assert
        Assert.True(requestCanceled);
        Assert.True(probe.RunCanceled);
        Assert.False(probe.DependencyDisposedWhenRunFinished);
    }

    private static async Task<WebApplication> StartRequestBoundAppAsync(RequestBoundRunProbe probe)
    {
        WebApplicationBuilder builder = CreateBuilder(validateScopes: true);
        builder.Services.AddScoped<DisposableRequestDependency>();
        builder.Services.AddKeyedScoped<AgentSessionStore>(
            BlockingAgent.AgentName,
            (_, _) => new DisposalTrackingSessionStore(probe));
        builder.AddOpenAIResponses();

        WebApplication app = builder.Build();
        app.Use(async (context, next) =>
        {
            try
            {
                await next(context);
            }
            finally
            {
                probe.RequestCompleted.TrySetResult();
            }
        });
        app.MapOpenAIResponses(
            "/v1/responses",
            context => new BlockingAgent(context.RequestServices.GetRequiredService<DisposableRequestDependency>(), probe));
        await app.StartAsync();
        return app;
    }

    private static async Task<bool> CompletesWithinAsync(Task task, TimeSpan timeout) =>
        await Task.WhenAny(task, Task.Delay(timeout)) == task;

    private static WebApplicationBuilder CreateBuilder(bool validateScopes = false)
    {
        var options = new WebApplicationOptions
        {
            EnvironmentName = validateScopes ? Environments.Development : Environments.Production
        };
        WebApplicationBuilder builder = WebApplication.CreateBuilder(options);
        builder.WebHost.UseTestServer();
        return builder;
    }

    private static Mock<IChatClient> CreateApprovalChatClient(Func<int> nextCall)
    {
        Mock<IChatClient> chatClient = new();
        chatClient
            .Setup(client => client.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions?>(),
                It.IsAny<CancellationToken>()))
            .Returns(() =>
            {
                AIContent content = nextCall() == 1
                    ? new FunctionCallContent("call-1", ToolName)
                    : new TextContent("Decision processed");
                return new ChatResponse([
                    new ChatMessage(ChatRole.Assistant, [content])
                ]).ToChatResponseUpdates().ToAsyncEnumerable();
            });
        return chatClient;
    }

    private static async Task<(string ResponseId, JsonElement ApprovalEvent)> CreatePendingApprovalAsync(
        HttpClient client,
        string path,
        bool includeAgentName)
    {
        string agentProperty = includeAgentName
            ? $$""" "agent": { "name": "{{AgentName}}" },"""
            : string.Empty;
        using StringContent content = JsonContent($$"""
            {
              {{agentProperty}}
              "input": "hello",
              "stream": true
            }
            """);
        using HttpResponseMessage response = await client.PostAsync(
            new Uri(path, UriKind.Relative),
            content);
        response.EnsureSuccessStatusCode();

        List<JsonElement> events = ParseSseEvents(await response.Content.ReadAsStringAsync());
        JsonElement approvalEvent = Assert.Single(events,
            item => item.GetProperty("type").GetString() == "response.function_approval.requested");
        string responseId = events.Last().GetProperty("response").GetProperty("id").GetString()!;
        return (responseId, approvalEvent);
    }

    private static string CreateApprovalResponseJson(
        string responseId,
        JsonElement approvalEvent,
        bool includeAgentName)
    {
        string agentProperty = includeAgentName
            ? $$""" "agent": { "name": "{{AgentName}}" },"""
            : string.Empty;
        return $$"""
            {
              {{agentProperty}}
              "previous_response_id": {{JsonSerializer.Serialize(responseId)}},
              "input": [{
                "type": "message",
                "role": "user",
                "content": [{
                  "type": "function_approval_response",
                  "request_id": {{approvalEvent.GetProperty("request_id").GetRawText()}},
                  "approved": true,
                  "function_call": {{approvalEvent.GetProperty("function_call").GetRawText()}}
                }]
              }]
            }
            """;
    }

    private static async Task<(string ResponseId, JsonElement ApprovalEvent)> ReadApprovalEventAsync(
        StreamReader reader)
    {
        string? responseId = null;
        while (await reader.ReadLineAsync() is { } line)
        {
            if (!line.StartsWith("data: ", StringComparison.Ordinal))
            {
                continue;
            }

            using JsonDocument document = JsonDocument.Parse(line["data: ".Length..]);
            JsonElement item = document.RootElement;
            string? type = item.GetProperty("type").GetString();
            if (type == "response.created")
            {
                responseId = item.GetProperty("response").GetProperty("id").GetString();
            }
            else if (type == "response.function_approval.requested")
            {
                return (Assert.IsType<string>(responseId), item.Clone());
            }
        }

        throw new InvalidOperationException("The stream ended before an approval request was emitted.");
    }

    private static List<JsonElement> ParseSseEvents(string content)
    {
        var events = new List<JsonElement>();
        foreach (string line in content.Split('\n'))
        {
            if (!line.StartsWith("data: ", StringComparison.Ordinal))
            {
                continue;
            }

            using JsonDocument document = JsonDocument.Parse(line["data: ".Length..]);
            events.Add(document.RootElement.Clone());
        }

        return events;
    }

    private static StringContent JsonContent(string json) =>
        new(json, Encoding.UTF8, "application/json");

    private static async Task<HttpResponseMessage> PostJsonAsync(
        HttpClient client,
        string path,
        string json,
        CancellationToken cancellationToken = default)
    {
        using StringContent content = JsonContent(json);
        return await client.PostAsync(new Uri(path, UriKind.Relative), content, cancellationToken);
    }

    private static async Task WaitForResponseCompletionAsync(
        HttpClient client,
        string path,
        string responseId)
    {
        for (int attempt = 0; attempt < 100; attempt++)
        {
            using HttpResponseMessage response = await client.GetAsync(
                new Uri($"{path}/{responseId}", UriKind.Relative));
            string responseBody = await response.Content.ReadAsStringAsync();
            response.EnsureSuccessStatusCode();
            using JsonDocument document = JsonDocument.Parse(responseBody);
            string? status = document.RootElement.GetProperty("status").GetString();
            if (status == "completed")
            {
                return;
            }

            if (status is "failed" or "cancelled" or "incomplete")
            {
                throw new InvalidOperationException(
                    $"Background response entered terminal status '{status}'.");
            }

            await Task.Delay(TimeSpan.FromMilliseconds(20));
        }

        throw new TimeoutException("Background response did not complete.");
    }

    private sealed class PausingApprovalAgent : AIAgent
    {
        private readonly TaskCompletionSource _releaseInitialRun =
            new(TaskCreationOptions.RunContinuationsAsynchronously);

        public override string Name => AgentName;

        public void ReleaseInitialRun() => this._releaseInitialRun.TrySetResult();

        protected override ValueTask<AgentSession> CreateSessionCoreAsync(
            CancellationToken cancellationToken = default) =>
            new(new TestSession());

        protected override ValueTask<JsonElement> SerializeSessionCoreAsync(
            AgentSession session,
            JsonSerializerOptions? jsonSerializerOptions = null,
            CancellationToken cancellationToken = default) =>
            new(session.StateBag.Serialize());

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(
            JsonElement serializedState,
            JsonSerializerOptions? jsonSerializerOptions = null,
            CancellationToken cancellationToken = default) =>
            new(new TestSession(AgentSessionStateBag.Deserialize(serializedState)));

        protected override Task<AgentResponse> RunCoreAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session = null,
            AgentRunOptions? options = null,
            CancellationToken cancellationToken = default) =>
            throw new NotSupportedException("This regression test uses streaming execution.");

        protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session = null,
            AgentRunOptions? options = null,
            [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            if (messages.SelectMany(message => message.Contents).OfType<ToolApprovalResponseContent>().Any())
            {
                yield return new AgentResponseUpdate(ChatRole.Assistant, "Decision processed");
                yield break;
            }

            yield return new AgentResponseUpdate
            {
                Role = ChatRole.Assistant,
                Contents = [
                    new ToolApprovalRequestContent(
                        "request-1",
                        new FunctionCallContent(
                            "call-1",
                            ToolName,
                            new Dictionary<string, object?>()))
                ]
            };

            await this._releaseInitialRun.Task.WaitAsync(cancellationToken);
        }

        private sealed class TestSession : AgentSession
        {
            public TestSession()
            {
            }

            public TestSession(AgentSessionStateBag stateBag)
                : base(stateBag)
            {
            }
        }
    }

    private sealed class ScopedSessionStoreTracker
    {
        private int _executionStoreRecorded;

        public TaskCompletionSource<TrackingSessionStore> ExecutionStoreCreated { get; } =
            new(TaskCreationOptions.RunContinuationsAsynchronously);

        public TrackingSessionStore CreateStore() => new(this);

        public void RecordExecutionStore(TrackingSessionStore store)
        {
            if (Interlocked.Exchange(ref this._executionStoreRecorded, 1) == 0)
            {
                this.ExecutionStoreCreated.TrySetResult(store);
            }
        }
    }

    private sealed class TrackingSessionStore : AgentSessionStore, IDisposable
    {
        private readonly InMemoryAgentSessionStore _inner = new();
        private readonly ScopedSessionStoreTracker _tracker;

        public TrackingSessionStore(ScopedSessionStoreTracker tracker)
        {
            this._tracker = tracker;
        }

        public TaskCompletionSource Disposed { get; } =
            new(TaskCreationOptions.RunContinuationsAsynchronously);

        public bool IsDisposed { get; private set; }

        public int SaveCount { get; private set; }

        public override ValueTask<AgentSession?> GetSessionAsync(
            AIAgent agent,
            AgentSessionStoreKey key,
            CancellationToken cancellationToken = default)
        {
            ObjectDisposedException.ThrowIf(this.IsDisposed, this);
            this._tracker.RecordExecutionStore(this);
            return this._inner.GetSessionAsync(agent, key, cancellationToken);
        }

        public override ValueTask SaveSessionAsync(
            AIAgent agent,
            AgentSessionStoreKey key,
            AgentSession session,
            CancellationToken cancellationToken = default)
        {
            ObjectDisposedException.ThrowIf(this.IsDisposed, this);
            this.SaveCount++;
            return this._inner.SaveSessionAsync(agent, key, session, cancellationToken);
        }

        public void Dispose()
        {
            this.IsDisposed = true;
            this.Disposed.TrySetResult();
        }
    }

    private sealed class TenantState
    {
        public string? Tenant { get; set; }
    }

    private sealed class TenantObservations
    {
        private readonly object _gate = new();
        private readonly List<TenantState> _agentStates = [];
        private readonly List<TenantState> _storeStates = [];
        private readonly List<string?> _storeOperationTenants = [];

        public IReadOnlyList<TenantState> AgentStates { get { lock (this._gate) { return [.. this._agentStates]; } } }

        public IReadOnlyList<TenantState> StoreStates { get { lock (this._gate) { return [.. this._storeStates]; } } }

        public IReadOnlyList<string?> StoreOperationTenants { get { lock (this._gate) { return [.. this._storeOperationTenants]; } } }

        public void RecordAgent(TenantState state)
        {
            lock (this._gate)
            {
                this._agentStates.Add(state);
            }
        }

        public void RecordStore(TenantState state)
        {
            lock (this._gate)
            {
                this._storeStates.Add(state);
            }
        }

        public void RecordStoreOperation(TenantState state)
        {
            lock (this._gate)
            {
                this._storeOperationTenants.Add(state.Tenant);
            }
        }
    }

    private sealed class TenantSessionStore : AgentSessionStore
    {
        private readonly InMemoryAgentSessionStore _inner = new();
        private readonly TenantState _tenant;
        private readonly TenantObservations _observations;

        public TenantSessionStore(TenantState tenant, TenantObservations observations)
        {
            this._tenant = tenant;
            this._observations = observations;
            observations.RecordStore(tenant);
        }

        public override ValueTask<AgentSession?> GetSessionAsync(
            AIAgent agent,
            AgentSessionStoreKey key,
            CancellationToken cancellationToken = default)
        {
            this._observations.RecordStoreOperation(this._tenant);
            return this._inner.GetSessionAsync(agent, key, cancellationToken);
        }

        public override ValueTask SaveSessionAsync(
            AIAgent agent,
            AgentSessionStoreKey key,
            AgentSession session,
            CancellationToken cancellationToken = default)
        {
            this._observations.RecordStoreOperation(this._tenant);
            return this._inner.SaveSessionAsync(agent, key, session, cancellationToken);
        }
    }

    private sealed class TenantAgent : StreamingTestAgent
    {
        public const string AgentName = "tenant-agent";

        private readonly TenantState _tenant;

        public TenantAgent(TenantState tenant, TenantObservations observations)
        {
            this._tenant = tenant;
            observations.RecordAgent(tenant);
        }

        public override string Name => AgentName;

        protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session = null,
            AgentRunOptions? options = null,
            [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            await Task.Yield();
            yield return new AgentResponseUpdate(ChatRole.Assistant, $"Hello {this._tenant.Tenant}");
        }
    }

    private sealed class RequestBoundRunProbe
    {
        public TimeSpan CleanupDelay { get; init; }

        public TaskCompletionSource AgentStarted { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);

        public TaskCompletionSource ReleaseAgent { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);

        public TaskCompletionSource RunFinished { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);

        public TaskCompletionSource SessionSaved { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);

        public TaskCompletionSource RequestCompleted { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);

        public bool RunCanceled { get; set; }

        public bool? DependencyDisposedWhenRunFinished { get; set; }

        public bool? StoreDisposedWhenSessionSaved { get; set; }
    }

    private sealed class DisposableRequestDependency : IDisposable
    {
        public bool IsDisposed { get; private set; }

        public void Dispose() => this.IsDisposed = true;
    }

    private sealed class DisposalTrackingSessionStore(RequestBoundRunProbe probe) : AgentSessionStore, IDisposable
    {
        private readonly InMemoryAgentSessionStore _inner = new();
        private bool _disposed;

        public override ValueTask<AgentSession?> GetSessionAsync(
            AIAgent agent,
            AgentSessionStoreKey key,
            CancellationToken cancellationToken = default) =>
            this._inner.GetSessionAsync(agent, key, cancellationToken);

        public override async ValueTask SaveSessionAsync(
            AIAgent agent,
            AgentSessionStoreKey key,
            AgentSession session,
            CancellationToken cancellationToken = default)
        {
            probe.StoreDisposedWhenSessionSaved = this._disposed;
            await this._inner.SaveSessionAsync(agent, key, session, cancellationToken);
            probe.SessionSaved.TrySetResult();
        }

        public void Dispose() => this._disposed = true;
    }

    private sealed class BlockingAgent(DisposableRequestDependency dependency, RequestBoundRunProbe probe) : StreamingTestAgent
    {
        public const string AgentName = "blocking-agent";

        public override string Name => AgentName;

        protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session = null,
            AgentRunOptions? options = null,
            [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            probe.AgentStarted.TrySetResult();
            try
            {
                await probe.ReleaseAgent.Task.WaitAsync(cancellationToken);
            }
            finally
            {
                probe.RunCanceled = cancellationToken.IsCancellationRequested;

                // Keep using the request-scoped dependency while the run unwinds.
                await Task.Delay(probe.CleanupDelay, CancellationToken.None);
                probe.DependencyDisposedWhenRunFinished = dependency.IsDisposed;
                probe.RunFinished.TrySetResult();
            }

            yield return new AgentResponseUpdate(ChatRole.Assistant, "done");
        }
    }

    /// <summary>
    /// An agent that persists its session state bag and only supports streaming runs.
    /// </summary>
    private abstract class StreamingTestAgent : AIAgent
    {
        protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default) =>
            new(new TestAgentSession());

        protected override ValueTask<JsonElement> SerializeSessionCoreAsync(
            AgentSession session,
            JsonSerializerOptions? jsonSerializerOptions = null,
            CancellationToken cancellationToken = default) =>
            new(session.StateBag.Serialize());

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(
            JsonElement serializedState,
            JsonSerializerOptions? jsonSerializerOptions = null,
            CancellationToken cancellationToken = default) =>
            new(new TestAgentSession(AgentSessionStateBag.Deserialize(serializedState)));

        protected override Task<AgentResponse> RunCoreAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session = null,
            AgentRunOptions? options = null,
            CancellationToken cancellationToken = default) =>
            throw new NotSupportedException("This regression test uses streaming execution.");

        private sealed class TestAgentSession : AgentSession
        {
            public TestAgentSession()
            {
            }

            public TestAgentSession(AgentSessionStateBag stateBag)
                : base(stateBag)
            {
            }
        }
    }
}
