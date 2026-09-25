// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.AgentServer.Responses;
using Azure.AI.AgentServer.Responses.Models;
using Azure.Core;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Extensions.Options;
using Moq;
using MeaiTextContent = Microsoft.Extensions.AI.TextContent;

namespace Microsoft.Agents.AI.Foundry.Hosting.UnitTests;

/// <summary>
/// Verifies that <see cref="AgentFrameworkResponseHandler"/> applies the toolbox consent link policy on
/// every path that surfaces an <c>oauth_consent_request</c>, and fails the response without exposing a
/// rejected link.
/// </summary>
[Collection(FoundryProjectEndpointEnvFixture.Name)]
public class OAuthConsentPolicyHandlerTests
{
    private const string AllowedOrigin = "https://auth.example.com";
    private const string AllowedLink = "https://auth.example.com/authorize?state=1";
    private const string OtherLink = "https://other.example.com/authorize?state=1";

    [Fact]
    public async Task CreateAsync_PendingConsentOutsideAllowlist_FailsWithoutSurfacingLinkAsync()
    {
        // Arrange
        await using var service = await CreatePendingConsentServiceAsync(OtherLink, [AllowedOrigin]);

        // Act
        var events = await RunAsync(new TestAgent(), service);

        // Assert
        AssertFailedWithoutLink(events, OtherLink);
    }

    [Fact]
    public async Task CreateAsync_PendingConsentMatchingAllowlist_SurfacesConsentRequestAsync()
    {
        // Arrange
        await using var service = await CreatePendingConsentServiceAsync(AllowedLink, [AllowedOrigin]);

        // Act
        var events = await RunAsync(new TestAgent(), service);

        // Assert
        AssertConsentSurfaced(events, AllowedLink);
    }

    [Fact]
    public async Task CreateAsync_PendingUnsafeConsentWithoutAllowlist_FailsWithoutSurfacingLinkAsync()
    {
        // Arrange: without an allowlist the safe-HTTPS check still applies.
        const string UnsafeLink = "http://external.example/authorize";
        await using var service = await CreatePendingConsentServiceAsync(UnsafeLink, allowedOrigins: null);

        // Act
        var events = await RunAsync(new TestAgent(), service);

        // Assert
        AssertFailedWithoutLink(events, UnsafeLink);
    }

    [Fact]
    public async Task CreateAsync_MarkerConsentOutsideAllowlist_FailsWithoutSurfacingLinkAsync()
    {
        // Arrange
        await using var service = await CreateStartedServiceAsync(
            [AllowedOrigin],
            toolboxNames: [],
            opener: (name, _, _) => Task.FromResult(
                new FoundryToolboxService.ToolboxOpenResult(
                    Cached: null,
                    Consents: [new McpConsentInfo(name, $"{name}.tool", OtherLink)])));
        var request = CreateRequest();
        request.Tools.Add(new MCPTool("marker") { ServerUrl = new Uri("foundry-toolbox://marker-a") });

        // Act
        var events = await RunAsync(new TestAgent(), service, request);

        // Assert
        AssertFailedWithoutLink(events, OtherLink);
    }

    [Fact]
    public async Task CreateAsync_PerCallConsentOutsideAllowlist_FailsWithoutSurfacingLinkAsync()
    {
        // Arrange
        await using var service = await CreateStartedServiceAsync([AllowedOrigin], toolboxNames: [], opener: null);

        // Act
        var events = await RunAsync(new ConsentRequiringAgent(OtherLink), service);

        // Assert
        AssertFailedWithoutLink(events, OtherLink);
    }

    [Fact]
    public async Task CreateAsync_PerCallConsentWithoutAllowlist_SurfacesConsentRequestAsync()
    {
        // Arrange
        await using var service = await CreateStartedServiceAsync(allowedOrigins: null, toolboxNames: [], opener: null);

        // Act
        var events = await RunAsync(new ConsentRequiringAgent(OtherLink), service);

        // Assert
        AssertConsentSurfaced(events, OtherLink);
    }

    private static void AssertFailedWithoutLink(List<ResponseStreamEvent> events, string rejectedLink)
    {
        Assert.DoesNotContain(events, e => e is ResponseOutputItemAddedEvent { Item: OAuthConsentRequestOutputItem });
        var failed = Assert.IsType<ResponseFailedEvent>(events[^1]);
        Assert.Contains("consent link policy", failed.Response.Error.Message);
        Assert.DoesNotContain(rejectedLink, failed.Response.Error.Message);
    }

    private static void AssertConsentSurfaced(List<ResponseStreamEvent> events, string consentLink)
    {
        var added = Assert.Single(events.OfType<ResponseOutputItemAddedEvent>(), e => e.Item is OAuthConsentRequestOutputItem);
        Assert.Equal(consentLink, Assert.IsType<OAuthConsentRequestOutputItem>(added.Item).ConsentLink);
        Assert.IsType<ResponseIncompleteEvent>(events[^1]);
    }

    private static Task<FoundryToolboxService> CreatePendingConsentServiceAsync(string consentLink, IList<string>? allowedOrigins)
        => CreateStartedServiceAsync(
            allowedOrigins,
            toolboxNames: ["tb"],
            opener: (name, _, _) => Task.FromResult(
                new FoundryToolboxService.ToolboxOpenResult(
                    Cached: null,
                    Consents: [new McpConsentInfo(name, $"{name}.tool", consentLink)])));

    private static async Task<FoundryToolboxService> CreateStartedServiceAsync(
        IList<string>? allowedOrigins,
        IList<string> toolboxNames,
        Func<string, string?, CancellationToken, Task<FoundryToolboxService.ToolboxOpenResult>>? opener)
    {
        var options = new FoundryToolboxOptions
        {
            StrictMode = false,
            EndpointOverride = "http://127.0.0.1:1/unused",
            AllowedOAuthConsentOrigins = allowedOrigins,
        };
        foreach (var name in toolboxNames)
        {
            options.ToolboxNames.Add(name);
        }

        var service = new FoundryToolboxService(Options.Create(options), Mock.Of<TokenCredential>())
        {
            ToolboxOpener = opener,
        };
        await service.StartAsync(CancellationToken.None);
        return service;
    }

    private static CreateResponse CreateRequest()
    {
        var request = new CreateResponse { Model = "test" };
        request.Input = BinaryData.FromObjectAsJson(new[]
        {
            new { type = "message", id = "msg_1", status = "completed", role = "user",
                  content = new[] { new { type = "input_text", text = "Hello" } } }
        });
        return request;
    }

    private static async Task<List<ResponseStreamEvent>> RunAsync(
        AIAgent agent,
        FoundryToolboxService toolboxService,
        CreateResponse? request = null)
    {
        var services = new ServiceCollection();
        services.AddSingleton<AgentSessionStore>(new InMemoryAgentSessionStore());
        services.AddSingleton(agent);
        services.AddSingleton<HostedSessionIsolationKeyProvider>(new FakeHostedSessionIsolationKeyProvider());
        var handler = new AgentFrameworkResponseHandler(
            services.BuildServiceProvider(),
            NullLogger<AgentFrameworkResponseHandler>.Instance,
            toolboxService);

        var context = new Mock<ResponseContext>("resp_" + new string('0', 46)) { CallBase = true };
        context.Setup(x => x.GetHistoryAsync(It.IsAny<CancellationToken>())).ReturnsAsync(Array.Empty<OutputItem>());
        context.Setup(x => x.GetInputItemsAsync(It.IsAny<bool>(), It.IsAny<CancellationToken>())).ReturnsAsync(Array.Empty<Item>());

        var events = new List<ResponseStreamEvent>();
        await foreach (var evt in handler.CreateAsync(request ?? CreateRequest(), context.Object, CancellationToken.None))
        {
            events.Add(evt);
        }

        return events;
    }

    private sealed class SimpleAgentSession : AgentSession
    {
    }

    private abstract class AgentBase : AIAgent
    {
        protected override Task<AgentResponse> RunCoreAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session,
            AgentRunOptions? options,
            CancellationToken cancellationToken = default) =>
            throw new NotImplementedException();

        protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default) =>
            new(new SimpleAgentSession());

        protected override ValueTask<JsonElement> SerializeSessionCoreAsync(
            AgentSession session,
            JsonSerializerOptions? jsonSerializerOptions,
            CancellationToken cancellationToken = default) =>
            new(JsonDocument.Parse("{}").RootElement);

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(
            JsonElement serializedState,
            JsonSerializerOptions? jsonSerializerOptions,
            CancellationToken cancellationToken = default) =>
            new(new SimpleAgentSession());
    }

    private sealed class TestAgent : AgentBase
    {
        protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session,
            AgentRunOptions? options,
            [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            await Task.Yield();
            yield return new AgentResponseUpdate { MessageId = "resp_msg_1", Contents = [new MeaiTextContent("hi")] };
        }
    }

    /// <summary>
    /// Mirrors <see cref="ConsentAwareMcpClientAIFunction"/> on a <c>-32006</c> response: records the
    /// consent on the request state, cancels the tool loop, and surfaces the cancellation.
    /// </summary>
    private sealed class ConsentRequiringAgent(string consentLink) : AgentBase
    {
        protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session,
            AgentRunOptions? options,
            [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            var state = McpConsentContext.Current.Value
                ?? throw new InvalidOperationException("The handler did not set the consent state.");
            state.Pending = new McpConsentInfo("tb", "tb.tool", consentLink);
            state.CancellationSource?.Cancel();
            await Task.Yield();
            cancellationToken.ThrowIfCancellationRequested();
            yield break;
        }
    }
}
