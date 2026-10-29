// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Azure.Core;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using Moq;

namespace Microsoft.Agents.AI.Foundry.Hosting.UnitTests;

public sealed class FoundryToolboxApprovalTests
{
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task RequiresToolApproval_ExistingApprovalService_ReturnsTrueAsync(bool delegated)
    {
        // Arrange
        AIFunction tool = new ApprovalRequiredAIFunction(AIFunctionFactory.Create(() => "Sunny", "get_weather"));
        if (delegated)
        {
            var wrapper = new Mock<AIFunction>();
            wrapper.Setup(f => f.GetService(typeof(ApprovalRequiredAIFunction), null)).Returns(tool);
            tool = wrapper.Object;
        }

        await using var service = new FoundryToolboxService(
            Options.Create(new FoundryToolboxOptions()),
            Mock.Of<TokenCredential>());

        // Act
        var requiresApproval = service.RequiresToolApproval(tool, "weather");

        // Assert
        Assert.True(requiresApproval);
    }

    [Theory]
    [InlineData(false, true)]
    [InlineData(false, false)]
    [InlineData(true, true)]
    [InlineData(true, false)]
    public async Task DiscoveredTool_RequiresDecisionForEachCallAsync(bool streaming, bool approved)
    {
        // Arrange
        await using var toolbox = await ToolboxServer.CreateAsync("""{"tool_configuration":{"require_approval":"always"}}""");
        await using var service = toolbox.CreateService();
        await service.StartAsync(CancellationToken.None);
        var tool = Assert.IsAssignableFrom<AIFunction>(Assert.Single(service.Tools));
        var calls = 0;
        ChatResponse NextResponse() => ++calls == 1 || calls == 3
            ? new(new ChatMessage(ChatRole.Assistant, [new FunctionCallContent(
                $"call-{calls}", tool.Name, new Dictionary<string, object?> { ["city"] = "Amsterdam" })]))
            : new(new ChatMessage(ChatRole.Assistant, "Done"));
        var client = new Mock<IChatClient>();
        client.Setup(c => c.GetResponseAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()))
            .Returns(() => Task.FromResult(NextResponse()));
        client.Setup(c => c.GetStreamingResponseAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()))
            .Returns(() => ToUpdatesAsync(NextResponse()));
        var agent = new ChatClientAgent(client.Object, new ChatClientAgentOptions
        {
            ChatOptions = new() { Tools = [tool] },
        });
        var session = await agent.CreateSessionAsync();

        // Act
        var response = await RunAsync(agent, session, [new(ChatRole.User, "Get the weather")], streaming);

        // Assert
        Assert.Equal(0, toolbox.InvocationCount);
        var request = Assert.Single(response.Messages.SelectMany(m => m.Contents).OfType<ToolApprovalRequestContent>());
        var call = Assert.IsType<FunctionCallContent>(request.ToolCall);
        Assert.Equal(tool.Name, call.Name);
        Assert.Equal("call-1", call.CallId);
        Assert.Equal("Amsterdam", Assert.IsType<string>(call.Arguments!["city"]));

        // Approval remains bound to the originally proposed arguments.
        call.Arguments["city"] = "Rotterdam";
        await RunAsync(agent, session, [new(ChatRole.User, [request.CreateResponse(approved)])], streaming);
        Assert.Equal(approved ? 1 : 0, toolbox.InvocationCount);
        if (approved)
        {
            Assert.Equal("Amsterdam", toolbox.LastArguments!["city"]!.GetValue<string>());
        }

        var next = await RunAsync(agent, session, [new(ChatRole.User, "Get the weather again")], streaming);
        Assert.Single(next.Messages.SelectMany(m => m.Contents).OfType<ToolApprovalRequestContent>());
        Assert.Equal(approved ? 1 : 0, toolbox.InvocationCount);
    }

    [Theory]
    [InlineData(null, false)]
    [InlineData("{}", false)]
    [InlineData("""{"unrelated":true}""", false)]
    [InlineData("""{"tool_configuration":{}}""", false)]
    [InlineData("""{"tool_configuration":{"require_approval":"never"}}""", false)]
    [InlineData("""{"tool_configuration":{"require_approval":"always"}}""", true)]
    [InlineData("""{"tool_configuration":{"require_approval":"unknown"}}""", true)]
    [InlineData("""{"tool_configuration":{"require_approval":""}}""", true)]
    [InlineData("""{"tool_configuration":{"require_approval":"ALWAYS"}}""", true)]
    [InlineData("""{"tool_configuration":{"require_approval":null}}""", true)]
    [InlineData("""{"tool_configuration":{"require_approval":false}}""", true)]
    [InlineData("""{"tool_configuration":{"require_approval":1}}""", true)]
    [InlineData("""{"tool_configuration":{"require_approval":[]}}""", true)]
    [InlineData("""{"tool_configuration":{"require_approval":{}}}""", true)]
    [InlineData("""{"tool_configuration":null}""", true)]
    [InlineData("""{"tool_configuration":[]}""", true)]
    [InlineData("""{"tool_configuration":"never"}""", true)]
    public async Task DiscoveredTool_ApprovalMetadataIsAppliedAsync(string? metadata, bool requiresApproval)
    {
        // Arrange
        await using var toolbox = await ToolboxServer.CreateAsync(metadata);
        await using var service = toolbox.CreateService();

        // Act
        await service.StartAsync(CancellationToken.None);
        var tool = Assert.IsAssignableFrom<AIFunction>(Assert.Single(service.Tools));

        // Assert
        Assert.Equal(requiresApproval, tool.GetService<ApprovalRequiredAIFunction>() is not null);
        Assert.Equal("get_weather", tool.Name);
        Assert.Equal("Gets the weather", tool.Description);
        Assert.True(tool.JsonSchema.GetProperty("properties").TryGetProperty("city", out _));
        Assert.Equal(0, toolbox.InvocationCount);
        if (!requiresApproval)
        {
            await tool.InvokeAsync(new AIFunctionArguments { ["city"] = "Amsterdam" });
            Assert.Equal(1, toolbox.InvocationCount);
        }
    }

    [Theory]
    [InlineData("lazy")]
    [InlineData("deferred")]
    [InlineData("consent")]
    public async Task RequestDiscoveredTool_RequiresApprovalAsync(string discoveryPath)
    {
        // Arrange
        await using var toolbox = await ToolboxServer.CreateAsync("""{"tool_configuration":{"require_approval":"always"}}""");
        if (discoveryPath is "deferred")
        {
            toolbox.ListError = new JsonObject { ["code"] = -32603, ["message"] = "Try again" };
        }
        else if (discoveryPath is "consent")
        {
            toolbox.ListError = new JsonObject
            {
                ["code"] = -32006,
                ["message"] = """tools/list failed {"errors":[{"name":"get_weather","type":"mcp","error":{"code":"CONSENT_REQUIRED","message":"https://auth.example.com/authorize"}}]}""",
            };
        }

        await using var service = toolbox.CreateService(preRegistered: discoveryPath is not "lazy");
        await service.StartAsync(CancellationToken.None);
        Assert.Empty(service.Tools);
        Assert.Equal(
            discoveryPath is "deferred" ? FoundryToolboxStartupStatus.Degraded :
            discoveryPath is "consent" ? FoundryToolboxStartupStatus.ConsentRequired : FoundryToolboxStartupStatus.Healthy,
            service.StartupStatus);
        toolbox.ListError = null;
        await using var scope = service.CreateRequestScope();
        var previousScope = HostedCallContext.ToolboxCacheScopeId;
        HostedCallContext.ToolboxCacheScopeId = scope.Id;
        try
        {
            // Act
            IReadOnlyList<AITool> tools;
            if (discoveryPath is "lazy")
            {
                tools = (await service.GetToolboxToolsAsync("weather", version: null, CancellationToken.None)).Tools;
            }
            else
            {
                if (discoveryPath is "deferred")
                {
                    await service.RetryDeferredToolboxesAsync(CancellationToken.None);
                }
                else
                {
                    Assert.Empty(await service.ResolvePendingConsentsAsync(CancellationToken.None));
                }

                tools = service.GetCurrentRequestTools();
            }

            // Assert
            Assert.NotNull(Assert.IsAssignableFrom<AIFunction>(Assert.Single(tools)).GetService<ApprovalRequiredAIFunction>());
            Assert.Empty(service.Tools);
            Assert.Equal(0, toolbox.InvocationCount);
        }
        finally
        {
            HostedCallContext.ToolboxCacheScopeId = previousScope;
        }
    }

    [Fact]
    public async Task DiscoveredTool_ApprovalWrapperPreservesConsentAsync()
    {
        // Arrange
        const string ConsentUrl = "https://auth.example.com/authorize";
        await using var toolbox = await ToolboxServer.CreateAsync("""{"tool_configuration":{"require_approval":"always"}}""");
        toolbox.CallError = new JsonObject { ["code"] = -32006, ["message"] = ConsentUrl };
        await using var service = toolbox.CreateService();
        await service.StartAsync(CancellationToken.None);
        var tool = Assert.IsType<ApprovalRequiredAIFunction>(Assert.Single(service.Tools));
        using var cancellation = new CancellationTokenSource();
        var state = new RequestConsentState { CancellationSource = cancellation };
        var previous = McpConsentContext.Current.Value;
        McpConsentContext.Current.Value = state;
        try
        {
            // Act
            await Assert.ThrowsAnyAsync<OperationCanceledException>(
                async () => await tool.InvokeAsync(new AIFunctionArguments { ["city"] = "Amsterdam" }, cancellation.Token));

            // Assert
            Assert.True(cancellation.IsCancellationRequested);
            Assert.NotNull(state.Pending);
            Assert.Equal("weather", state.Pending.ToolboxName);
            Assert.Equal("get_weather", state.Pending.ToolName);
            Assert.EndsWith(ConsentUrl, state.Pending.ConsentUrl, StringComparison.Ordinal);
            Assert.Equal(1, toolbox.InvocationCount);
        }
        finally
        {
            McpConsentContext.Current.Value = previous;
        }
    }

    private static async Task<AgentResponse> RunAsync(
        AIAgent agent, AgentSession session, IEnumerable<ChatMessage> messages, bool streaming)
    {
        if (!streaming)
        {
            return await agent.RunAsync(messages, session);
        }

        return await agent.RunStreamingAsync(messages, session).ToAgentResponseAsync();
    }

    private static async IAsyncEnumerable<ChatResponseUpdate> ToUpdatesAsync(ChatResponse response)
    {
        await Task.CompletedTask;
        foreach (var update in response.ToChatResponseUpdates())
        {
            yield return update;
        }
    }

    private sealed class ToolboxServer(WebApplication app) : IAsyncDisposable
    {
        internal int InvocationCount { get; private set; }
        internal JsonNode? LastArguments { get; private set; }
        internal JsonObject? ListError { get; set; }
        internal JsonObject? CallError { get; set; }

        internal static async Task<ToolboxServer> CreateAsync(string? metadata)
        {
            var builder = WebApplication.CreateBuilder();
            builder.WebHost.UseUrls("http://127.0.0.1:0");
            builder.Logging.ClearProviders();
            builder.Logging.AddConsole();
            builder.Logging.SetMinimumLevel(LogLevel.Warning);
            var app = builder.Build();
            var server = new ToolboxServer(app);
            app.Run(async context =>
            {
                if (!HttpMethods.IsPost(context.Request.Method))
                {
                    context.Response.StatusCode = StatusCodes.Status405MethodNotAllowed;
                    return;
                }

                var request = (await JsonNode.ParseAsync(context.Request.Body, cancellationToken: context.RequestAborted))!;
                if (request["id"] is null)
                {
                    context.Response.StatusCode = StatusCodes.Status202Accepted;
                    return;
                }

                JsonNode result;
                switch (request["method"]!.GetValue<string>())
                {
                    case "initialize":
                        result = new JsonObject
                        {
                            ["protocolVersion"] = request["params"]!["protocolVersion"]!.DeepClone(),
                            ["capabilities"] = new JsonObject { ["tools"] = new JsonObject() },
                            ["serverInfo"] = new JsonObject { ["name"] = "test-toolbox", ["version"] = "1.0" },
                        };
                        break;
                    case "tools/list":
                        if (server.ListError is { } listError)
                        {
                            await WriteErrorAsync(context, request["id"]!, listError);
                            return;
                        }

                        var tool = JsonNode.Parse("""
                            {"name":"get_weather","description":"Gets the weather",
                             "inputSchema":{"type":"object","properties":{"city":{"type":"string"}},"required":["city"]}}
                            """)!;
                        if (metadata is not null)
                        {
                            tool["_meta"] = JsonNode.Parse(metadata);
                        }

                        result = new JsonObject { ["tools"] = new JsonArray(tool) };
                        break;
                    case "tools/call":
                        server.InvocationCount++;
                        server.LastArguments = request["params"]!["arguments"]!.DeepClone();
                        if (server.CallError is { } callError)
                        {
                            await WriteErrorAsync(context, request["id"]!, callError);
                            return;
                        }

                        result = JsonNode.Parse("""{"content":[{"type":"text","text":"Sunny"}]}""")!;
                        break;
                    default:
                        await WriteErrorAsync(context, request["id"]!, new JsonObject { ["code"] = -32601, ["message"] = "Method not found" });
                        return;
                }

                await context.Response.WriteAsJsonAsync(new JsonObject
                {
                    ["jsonrpc"] = "2.0",
                    ["id"] = request["id"]!.DeepClone(),
                    ["result"] = result,
                }, context.RequestAborted);
            });
            await app.StartAsync();
            return server;
        }

        private static Task WriteErrorAsync(HttpContext context, JsonNode id, JsonObject error) =>
            context.Response.WriteAsJsonAsync(new JsonObject
            {
                ["jsonrpc"] = "2.0",
                ["id"] = id.DeepClone(),
                ["error"] = error.DeepClone(),
            }, context.RequestAborted);

        internal FoundryToolboxService CreateService(bool preRegistered = true)
        {
            var credential = new Mock<TokenCredential>();
            credential.Setup(c => c.GetTokenAsync(It.IsAny<TokenRequestContext>(), It.IsAny<CancellationToken>()))
                .ReturnsAsync(new AccessToken("test-token", DateTimeOffset.UtcNow.AddHours(1)));
            var options = new FoundryToolboxOptions
            {
                EndpointOverride = app.Urls.Single(),
                StrictMode = preRegistered,
            };
            if (preRegistered)
            {
                options.ToolboxNames.Add("weather");
            }

            return new FoundryToolboxService(
                Options.Create(options),
                credential.Object,
                app.Services.GetRequiredService<ILogger<FoundryToolboxService>>());
        }

        public ValueTask DisposeAsync() => app.DisposeAsync();
    }
}
