// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel;
using System.ClientModel.Primitives;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using OpenAI.Responses;

namespace Microsoft.Agents.AI.Hosting.OpenAI.UnitTests;

public sealed class AgentHostingServiceCollectionExtensionsTests
{
    [Fact]
    public async Task HostedWebSearchTool_WithResponsesClient_UsesResponsesWireFormatAsync()
    {
        // Arrange
        using var handler = new RecordingHandler();
#pragma warning disable CA5399
        using var httpClient = new HttpClient(handler);
#pragma warning restore CA5399
        using IChatClient chatClient = new ResponsesClient(
            new ApiKeyCredential("test-key"),
            new ResponsesClientOptions
            {
                Endpoint = new Uri("https://example.test/v1"),
                Transport = new HttpClientPipelineTransport(httpClient)
            })
            .AsIChatClientWithStoredOutputDisabled(model: "test-model");

        var services = new ServiceCollection();
        services
            .AddAIAgent("test-agent", "You are a helpful assistant.", chatClient)
            .WithAITool(new HostedWebSearchTool());
        using ServiceProvider serviceProvider = services.BuildServiceProvider();
        AIAgent agent = serviceProvider.GetRequiredKeyedService<AIAgent>("test-agent");

        // Act
        await agent.RunAsync("What happened in the news today?");

        // Assert
        using JsonDocument request = JsonDocument.Parse(Assert.IsType<string>(handler.RequestBody));
        Assert.False(request.RootElement.GetProperty("store").GetBoolean());
        Assert.Contains(
            request.RootElement.GetProperty("include").EnumerateArray(),
            property => property.GetString() == "reasoning.encrypted_content");
        Assert.False(request.RootElement.TryGetProperty("web_search_options", out _));
        JsonElement webSearchTool = Assert.Single(request.RootElement.GetProperty("tools").EnumerateArray());
        Assert.Equal("web_search", webSearchTool.GetProperty("type").GetString());
        Assert.Equal("/v1/responses", handler.RequestUri?.AbsolutePath);
    }

    private sealed class RecordingHandler : HttpMessageHandler
    {
        public Uri? RequestUri { get; private set; }

        public string? RequestBody { get; private set; }

        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            this.RequestUri = request.RequestUri;
            this.RequestBody = await request.Content!.ReadAsStringAsync(cancellationToken);

            return new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent(
                    """
                    {
                      "id": "resp_1",
                      "object": "response",
                      "created_at": 1700000000,
                      "status": "completed",
                      "model": "test-model",
                      "output": [],
                      "usage": {
                        "input_tokens": 1,
                        "output_tokens": 1,
                        "total_tokens": 2
                      }
                    }
                    """,
                    Encoding.UTF8,
                    "application/json"),
                RequestMessage = request
            };
        }
    }
}
