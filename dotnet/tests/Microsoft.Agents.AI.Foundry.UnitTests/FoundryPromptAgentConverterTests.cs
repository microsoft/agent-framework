// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel.Primitives;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.Extensions.OpenAI;
using Azure.AI.Projects;
using Azure.AI.Projects.Agents;
using Microsoft.Extensions.AI;
using OpenAI.Responses;

#pragma warning disable OPENAI001, CS0618

namespace Microsoft.Agents.AI.Foundry.UnitTests;

/// <summary>
/// Unit tests for the public <c>ToPromptAgentAsync</c> extension methods on
/// <see cref="ChatClientAgent"/> and <see cref="FoundryAgent"/>. Both entry points dispatch
/// to the same internal converter, so each behavior is asserted through both surfaces.
/// </summary>
public sealed class FoundryPromptAgentConverterTests
{
    // ----- Failure modes (assert through ChatClientAgent and FoundryAgent extensions) -----

    [Fact]
    public async Task ToPromptAgentAsync_ChatClientAgent_NonFoundryChatClient_ThrowsInvalidOperationExceptionAsync()
    {
        var agent = new ChatClientAgent(new NoOpChatClient());
        var ex = await Assert.ThrowsAsync<InvalidOperationException>(() => agent.ToPromptAgentAsync());
        Assert.Contains("FoundryChatClient", ex.Message);
    }

    [Fact]
    public async Task ToPromptAgentAsync_FoundryAgent_FoundryChatClientInMode3_ThrowsInvalidOperationExceptionAsync()
    {
        var foundryAgent = new FoundryAgent(
            agentEndpoint: new Uri("https://example.com/api/projects/myproj/agents/myagent/endpoint/protocols/openai"),
            credential: new FakeAuthenticationTokenProvider());
        var ex = await Assert.ThrowsAsync<InvalidOperationException>(() => foundryAgent.ToPromptAgentAsync());
        Assert.Contains("Agent Endpoint mode (Mode 3)", ex.Message);
    }

    [Fact]
    public async Task ToPromptAgentAsync_ChatClientAgent_Mode1_MissingModelId_ThrowsInvalidOperationExceptionAsync()
    {
        var projectClient = CreateProjectClient();
        // Construct a FoundryChatClient via the Responses Agent mode (Mode 1) then wrap in a ChatClientAgent whose
        // ChatOptions has no ModelId — synthesis must throw.
        var fcc = new FoundryChatClient(projectClient, "gpt-4o-mini");
        var agent = new ChatClientAgent(fcc, new ChatClientAgentOptions { ChatOptions = new ChatOptions() });
        var ex = await Assert.ThrowsAsync<InvalidOperationException>(() => agent.ToPromptAgentAsync());
        Assert.Contains("model id", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task ToPromptAgentAsync_ChatClientAgent_Mode1_UnsupportedAITool_ThrowsInvalidOperationExceptionNamingTypeAsync()
    {
        var projectClient = CreateProjectClient();
        var fcc = new FoundryChatClient(projectClient, "gpt-4o-mini");
        var agent = new ChatClientAgent(fcc, new ChatClientAgentOptions
        {
            ChatOptions = new ChatOptions
            {
                ModelId = "gpt-4o-mini",
                Tools = new System.Collections.Generic.List<AITool> { new UnsupportedTool() },
            },
        });
        var ex = await Assert.ThrowsAsync<InvalidOperationException>(() => agent.ToPromptAgentAsync());
        Assert.Contains(nameof(UnsupportedTool), ex.Message);
    }

    [Fact]
    public async Task ToPromptAgentAsync_FoundryAgent_HonorsCancellationAsync()
    {
        // Cancellation should bubble up from the AgentReference fetch path. Construct a
        // FoundryAgent via AsAIAgent(AgentReference) and pass a pre-cancelled token.
        var (foundryAgent, _) = CreateMode2_PromptAgentOnly("agent-name");
        using var cts = new CancellationTokenSource();
        cts.Cancel();
        await Assert.ThrowsAnyAsync<Exception>(() => foundryAgent.ToPromptAgentAsync(cts.Token));
    }

    // ----- the Responses Agent mode (Mode 1) (RAPI) synthesis paths -----

    [Fact]
    public async Task ToPromptAgentAsync_ChatClientAgent_Mode1_RoundTripsModelInstructionsTemperatureTopPAsync()
    {
        var projectClient = CreateProjectClient();
        var fcc = new FoundryChatClient(projectClient, "gpt-4o-mini");
        var agent = new ChatClientAgent(fcc, new ChatClientAgentOptions
        {
            ChatOptions = new ChatOptions
            {
                ModelId = "gpt-4o-mini",
                Instructions = "Be helpful.",
                Temperature = 0.5f,
                TopP = 0.9f,
            },
        });

        var def = await agent.ToPromptAgentAsync();
        var declarative = Assert.IsType<DeclarativeAgentDefinition>(def);
        Assert.Equal("gpt-4o-mini", declarative.Model);
        Assert.Equal("Be helpful.", declarative.Instructions);
        Assert.Equal(0.5f, declarative.Temperature);
        Assert.Equal(0.9f, declarative.TopP);
        Assert.Empty(declarative.Tools);
    }

    [Fact]
    public async Task ToPromptAgentAsync_ChatClientAgent_Mode1_NoTools_ReturnsDefinitionWithEmptyToolsAsync()
    {
        var projectClient = CreateProjectClient();
        var fcc = new FoundryChatClient(projectClient, "gpt-4o-mini");
        var agent = new ChatClientAgent(fcc, new ChatClientAgentOptions
        {
            ChatOptions = new ChatOptions { ModelId = "gpt-4o-mini" },
        });
        var def = await agent.ToPromptAgentAsync();
        var declarative = Assert.IsType<DeclarativeAgentDefinition>(def);
        Assert.Empty(declarative.Tools);
    }

    [Fact]
    public async Task ToPromptAgentAsync_ChatClientAgent_Mode1_AIFunctionTool_ConvertsToFunctionToolAsync()
    {
        var projectClient = CreateProjectClient();
        var fcc = new FoundryChatClient(projectClient, "gpt-4o-mini");
        var function = AIFunctionFactory.Create(() => "ok", "my_function", "A documented function.");
        var agent = new ChatClientAgent(fcc, new ChatClientAgentOptions
        {
            ChatOptions = new ChatOptions
            {
                ModelId = "gpt-4o-mini",
                Tools = new System.Collections.Generic.List<AITool> { function },
            },
        });

        var def = await agent.ToPromptAgentAsync();
        var declarative = Assert.IsType<DeclarativeAgentDefinition>(def);
        var fnTool = Assert.Single(declarative.Tools);
        var ft = Assert.IsType<FunctionTool>(fnTool);
        Assert.Equal("my_function", ft.FunctionName);
        Assert.Equal("A documented function.", ft.FunctionDescription);
    }

    [Fact]
    public async Task ToPromptAgentAsync_ChatClientAgent_Mode1_FoundryAITool_UnwrapsUnderlyingResponseToolAsync()
    {
        var projectClient = CreateProjectClient();
        var fcc = new FoundryChatClient(projectClient, "gpt-4o-mini");
        var agent = new ChatClientAgent(fcc, new ChatClientAgentOptions
        {
            ChatOptions = new ChatOptions
            {
                ModelId = "gpt-4o-mini",
                Tools = new System.Collections.Generic.List<AITool> { FoundryAITool.CreateWebSearchTool() },
            },
        });

        var def = await agent.ToPromptAgentAsync();
        var declarative = Assert.IsType<DeclarativeAgentDefinition>(def);
        var tool = Assert.Single(declarative.Tools);
        // The unwrapped instance must be the concrete WebSearchTool from the OpenAI SDK.
        Assert.IsType<WebSearchTool>(tool);
    }

    [Fact]
    public async Task ToPromptAgentAsync_ChatClientAgent_Mode1_MultipleToolsMixed_ConvertsAllInOrderAsync()
    {
        var projectClient = CreateProjectClient();
        var fcc = new FoundryChatClient(projectClient, "gpt-4o-mini");
        var function = AIFunctionFactory.Create(() => "ok", "fn", "");
        var agent = new ChatClientAgent(fcc, new ChatClientAgentOptions
        {
            ChatOptions = new ChatOptions
            {
                ModelId = "gpt-4o-mini",
                Tools = new System.Collections.Generic.List<AITool> { function, FoundryAITool.CreateWebSearchTool() },
            },
        });

        var def = await agent.ToPromptAgentAsync();
        var declarative = Assert.IsType<DeclarativeAgentDefinition>(def);
        Assert.Equal(2, declarative.Tools.Count);
        Assert.IsType<FunctionTool>(declarative.Tools[0]);
        Assert.IsType<WebSearchTool>(declarative.Tools[1]);
    }

    [Fact]
    public async Task ToPromptAgentAsync_FoundryAgent_Mode1_ResultIsDeclarativeAgentDefinitionAsync()
    {
        // FoundryAgent constructed via the projectEndpoint+model+instructions ctor (Responses Agent mode, the Responses Agent mode (Mode 1)).
        var foundryAgent = new FoundryAgent(
            projectEndpoint: new Uri("https://test.openai.azure.com/"),
            credential: new FakeAuthenticationTokenProvider(),
            model: "gpt-4o-mini",
            instructions: "You are helpful.");

        var def = await foundryAgent.ToPromptAgentAsync();
        var declarative = Assert.IsType<DeclarativeAgentDefinition>(def);
        Assert.Equal("gpt-4o-mini", declarative.Model);
        Assert.Equal("You are helpful.", declarative.Instructions);
    }

    // ----- the Prompt Agent mode (Mode 2) paths -----

    [Fact]
    public async Task ToPromptAgentAsync_FoundryAgent_Mode2_AgentVersion_ReturnsCachedDefinitionAsync()
    {
        // Construct via ProjectsAgentVersion → the Definition reference must come back unchanged.
        var version = ModelReaderWriter.Read<ProjectsAgentVersion>(BinaryData.FromString(TestDataUtil.GetAgentVersionResponseJson()))!;
        var projectClient = CreateProjectClient();
        var foundryAgent = projectClient.AsAIAgent(version);

        var def = await foundryAgent.ToPromptAgentAsync();
        Assert.Same(version.Definition, def);
    }

    [Fact]
    public async Task ToPromptAgentAsync_FoundryAgent_Mode2_AgentRecord_ReturnsLatestVersionDefinitionAsync()
    {
        var record = ModelReaderWriter.Read<ProjectsAgentRecord>(BinaryData.FromString(TestDataUtil.GetAgentResponseJson()))!;
        var projectClient = CreateProjectClient();
        var foundryAgent = projectClient.AsAIAgent(record);

        var def = await foundryAgent.ToPromptAgentAsync();
        Assert.Same(record.GetLatestVersion().Definition, def);
    }

    [Fact]
    public async Task ToPromptAgentAsync_FoundryAgent_Mode2_PromptAgentOnly_FetchesLatestVersionAsync()
    {
        // The handler returns a known agent JSON. The converter must hit GET /agents/{name}
        // and return that record's latest version definition.
        var fetched = false;
        using var handler = new HttpHandlerAssert(req =>
        {
            if (req.Method == HttpMethod.Get && req.RequestUri!.AbsolutePath.Contains("/agents/agent-name"))
            {
                fetched = true;
                return new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new StringContent(TestDataUtil.GetAgentResponseJson(agentName: "agent-name"), Encoding.UTF8, "application/json"),
                };
            }
            return new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent("{}", Encoding.UTF8, "application/json") };
        });
#pragma warning disable CA5399
        using var httpClient = new HttpClient(handler);
#pragma warning restore CA5399
        var projectClient = new AIProjectClient(
            new Uri("https://test.openai.azure.com/"),
            new FakeAuthenticationTokenProvider(),
            new AIProjectClientOptions { Transport = new HttpClientPipelineTransport(httpClient) });
        var foundryAgent = projectClient.AsAIAgent(new AgentReference("agent-name"));

        var def = await foundryAgent.ToPromptAgentAsync();
        Assert.True(fetched);
        Assert.NotNull(def);
    }

    [Fact]
    public async Task ToPromptAgentAsync_FoundryAgent_Mode2_PromptAgentOnly_PinnedVersion_FetchesPinnedVersionAsync()
    {
        // Q-C regression: when AgentReference.Version is set, the converter must call
        // GET /agents/{name}/versions/{version} and return that pinned version's definition,
        // NOT GET /agents/{name} -> GetLatestVersion() which would silently substitute the
        // server's latest. We probe both paths from the same handler and assert exactly one was hit.
        var fetchedLatest = false;
        var fetchedPinned = false;
        using var handler = new HttpHandlerAssert(req =>
        {
            // Pinned-version path: …/agents/{name}/versions/{version}
            if (req.Method == HttpMethod.Get && req.RequestUri!.AbsolutePath.Contains("/agents/agent-name/versions/2", StringComparison.Ordinal))
            {
                fetchedPinned = true;
                var pinnedDef = new DeclarativeAgentDefinition("gpt-pinned") { Instructions = "Pinned-version instructions." };
                return new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new StringContent(TestDataUtil.GetAgentVersionResponseJson(agentName: "agent-name", agentDefinition: pinnedDef), Encoding.UTF8, "application/json"),
                };
            }
            // Latest-version path: …/agents/{name}
            if (req.Method == HttpMethod.Get && req.RequestUri!.AbsolutePath.EndsWith("/agents/agent-name", StringComparison.Ordinal))
            {
                fetchedLatest = true;
                var latestDef = new DeclarativeAgentDefinition("gpt-latest") { Instructions = "Latest-version instructions." };
                return new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new StringContent(TestDataUtil.GetAgentResponseJson(agentName: "agent-name", agentDefinition: latestDef), Encoding.UTF8, "application/json"),
                };
            }
            return new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent("{}", Encoding.UTF8, "application/json") };
        });
#pragma warning disable CA5399
        using var httpClient = new HttpClient(handler);
#pragma warning restore CA5399
        var projectClient = new AIProjectClient(
            new Uri("https://test.openai.azure.com/"),
            new FakeAuthenticationTokenProvider(),
            new AIProjectClientOptions { Transport = new HttpClientPipelineTransport(httpClient) });
        var foundryAgent = projectClient.AsAIAgent(new AgentReference("agent-name", "2"));

        var def = await foundryAgent.ToPromptAgentAsync();

        Assert.True(fetchedPinned, "Pinned-version endpoint (.../agents/agent-name/versions/2) must be called when AgentReference.Version is set.");
        Assert.False(fetchedLatest, "Latest-version endpoint (.../agents/agent-name) must NOT be called when AgentReference.Version is set.");
        var declarative = Assert.IsType<DeclarativeAgentDefinition>(def);
        Assert.Equal("gpt-pinned", declarative.Model);
        Assert.Equal("Pinned-version instructions.", declarative.Instructions);
    }

    [Fact]
    public async Task ToPromptAgentAsync_FoundryAgent_Mode2_PromptAgentOnly_UnpinnedVersionKeyword_FetchesLatestAsync()
    {
        // Q-C boundary: AgentReference.Version == "latest" must fall back to the GET /agents/{name}
        // path (the latest-version path), NOT GET /agents/{name}/versions/latest.
        var fetchedLatest = false;
        using var handler = new HttpHandlerAssert(req =>
        {
            if (req.Method == HttpMethod.Get && req.RequestUri!.AbsolutePath.EndsWith("/agents/agent-name", StringComparison.Ordinal))
            {
                fetchedLatest = true;
                return new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new StringContent(TestDataUtil.GetAgentResponseJson(agentName: "agent-name"), Encoding.UTF8, "application/json"),
                };
            }
            return new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent("{}", Encoding.UTF8, "application/json") };
        });
#pragma warning disable CA5399
        using var httpClient = new HttpClient(handler);
#pragma warning restore CA5399
        var projectClient = new AIProjectClient(
            new Uri("https://test.openai.azure.com/"),
            new FakeAuthenticationTokenProvider(),
            new AIProjectClientOptions { Transport = new HttpClientPipelineTransport(httpClient) });
        var foundryAgent = projectClient.AsAIAgent(new AgentReference("agent-name", "latest"));

        var def = await foundryAgent.ToPromptAgentAsync();

        Assert.True(fetchedLatest);
        Assert.NotNull(def);
    }

    [Fact]
    public async Task ToPromptAgentAsync_FoundryAgent_Mode2_PromptAgentOnly_ServerReturnsError_PropagatesExceptionAsync()
    {
        using var handler = new HttpHandlerAssert(req =>
            new HttpResponseMessage(HttpStatusCode.NotFound) { Content = new StringContent("{\"error\":{\"code\":\"NotFound\"}}", Encoding.UTF8, "application/json") });
#pragma warning disable CA5399
        using var httpClient = new HttpClient(handler);
#pragma warning restore CA5399
        var projectClient = new AIProjectClient(
            new Uri("https://test.openai.azure.com/"),
            new FakeAuthenticationTokenProvider(),
            new AIProjectClientOptions { Transport = new HttpClientPipelineTransport(httpClient) });
        var foundryAgent = projectClient.AsAIAgent(new AgentReference("missing-agent"));

        await Assert.ThrowsAnyAsync<Exception>(() => foundryAgent.ToPromptAgentAsync());
    }

    // ----- Python-parity guard: both extensions produce equivalent definitions -----

    [Fact]
    public async Task BothExtensions_ProduceEquivalentDefinitions_ForEquivalentInputsAsync()
    {
        // Build two agents that are semantically equivalent: one as a plain ChatClientAgent
        // via AsAIAgent(model, instructions), and one as a FoundryAgent via the projectEndpoint
        // ctor. Both flow through the same converter; assert key fields match.
        var projectClient = CreateProjectClient();
        ChatClientAgent ccaAgent = projectClient.AsAIAgent("gpt-4o-mini", "Be helpful.");
        var foundryAgent = new FoundryAgent(
            projectEndpoint: new Uri("https://test.openai.azure.com/"),
            credential: new FakeAuthenticationTokenProvider(),
            model: "gpt-4o-mini",
            instructions: "Be helpful.");

        var ccaDef = await ccaAgent.ToPromptAgentAsync();
        var faDef = await foundryAgent.ToPromptAgentAsync();

        var a = Assert.IsType<DeclarativeAgentDefinition>(ccaDef);
        var b = Assert.IsType<DeclarativeAgentDefinition>(faDef);
        Assert.Equal(a.Model, b.Model);
        Assert.Equal(a.Instructions, b.Instructions);
        Assert.Equal(a.Tools.Count, b.Tools.Count);
    }

    // ----- Helpers -----

    private static AIProjectClient CreateProjectClient()
        => new(
            new Uri("https://test.openai.azure.com/"),
            new FakeAuthenticationTokenProvider(),
            new AIProjectClientOptions { Transport = new HttpClientPipelineTransport(new HttpClient()) });

    private static (FoundryAgent FoundryAgent, AIProjectClient ProjectClient) CreateMode2_PromptAgentOnly(string agentName)
    {
        var projectClient = CreateProjectClient();
        var foundryAgent = projectClient.AsAIAgent(new AgentReference(agentName));
        return (foundryAgent, projectClient);
    }

    private sealed class NoOpChatClient : IChatClient
    {
        public Task<ChatResponse> GetResponseAsync(System.Collections.Generic.IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default)
            => Task.FromResult(new ChatResponse());

        public System.Collections.Generic.IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(System.Collections.Generic.IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default)
            => EmptyAsyncEnumerableAsync();

        private static async System.Collections.Generic.IAsyncEnumerable<ChatResponseUpdate> EmptyAsyncEnumerableAsync()
        {
            await Task.CompletedTask.ConfigureAwait(false);
            yield break;
        }

        public object? GetService(Type serviceType, object? serviceKey = null) => null;

        public void Dispose() { }
    }

    private sealed class UnsupportedTool : AITool
    {
        public override string Name => "unsupported";
    }
}
#pragma warning restore CS0618
