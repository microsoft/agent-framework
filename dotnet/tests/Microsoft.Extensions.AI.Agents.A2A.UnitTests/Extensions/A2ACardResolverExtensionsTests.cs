// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections;
using System.Collections.Generic;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using A2A;

namespace Microsoft.Extensions.AI.Agents.A2A.UnitTests;

/// <summary>
/// Unit tests for the <see cref="A2ACardResolverExtensions"/> class.
/// </summary>
public sealed class A2ACardResolverExtensionsTests : IDisposable
{
    private readonly HttpClient _httpClient;
    private readonly HttpMessageHandlerStub _handler;
    private readonly A2ACardResolver _resolver;

    public A2ACardResolverExtensionsTests()
    {
        this._handler = new HttpMessageHandlerStub();
        this._httpClient = new HttpClient(this._handler, false);
        this._resolver = new A2ACardResolver(new Uri("http://test-host"), httpClient: this._httpClient);
    }

    [Fact]
    public async Task GetAIAgentAsync_WithValidAgentCard_ReturnsAIAgentAsync()
    {
        // Arrange
        this._handler.ResponsesToReturn.Enqueue(new AgentCard
        {
            Name = "Test Agent",
            Description = "A test agent for unit testing",
            Url = "http://test-endpoint/agent"
        });

        // Act
        var agent = await this._resolver.GetAIAgentAsync();

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<A2AAgent>(agent);
        Assert.Equal("Test Agent", agent.Name);
        Assert.Equal("A test agent for unit testing", agent.Description);

        // Verify that there was only one request made to retrieve the agent card
        Assert.Single(this._handler.CapturedUris);
        Assert.StartsWith("http://test-host/", this._handler.CapturedUris[0].ToString());
    }

    [Fact]
    public async Task RunIAgentAsync_WithUrlFromAgentCard_SendsRequestToTheUrlAsync()
    {
        // Arrange
        this._handler.ResponsesToReturn.Enqueue(new AgentCard
        {
            Url = "http://test-endpoint/agent"
        });
        this._handler.ResponsesToReturn.Enqueue(new Message
        {
            Role = MessageRole.Agent,
            Parts = [new TextPart { Text = "Response" }],
        });

        var agent = await this._resolver.GetAIAgentAsync(this._httpClient);

        // Act
        await agent.RunAsync("Test input");

        // Assert
        Assert.Equal(2, this._handler.CapturedUris.Count); // One for getting the card, one for sending the message to the agent
        Assert.Equal(new Uri("http://test-endpoint/agent"), this._handler.CapturedUris[1]);
    }

    public void Dispose()
    {
        this._handler.Dispose();
        this._httpClient.Dispose();
    }

    internal sealed class HttpMessageHandlerStub : HttpMessageHandler
    {
        public Queue ResponsesToReturn { get; } = new();

        public List<Uri> CapturedUris { get; } = [];

        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            this.CapturedUris.Add(request.RequestUri!);

            var response = this.ResponsesToReturn.Dequeue();

            if (response is AgentCard agentCard)
            {
                var json = JsonSerializer.Serialize(agentCard);
                return new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new StringContent(json, Encoding.UTF8, "application/json")
                };
            }
            else if (response is Message message)
            {
                var jsonRpcResponse = JsonRpcResponse.CreateJsonRpcResponse<A2AEvent>("response-id", message);

                return new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new StringContent(JsonSerializer.Serialize(jsonRpcResponse), Encoding.UTF8, "application/json")
                };
            }

            // Return empty agent card if none specified
            var emptyCard = new AgentCard();
            var emptyJson = JsonSerializer.Serialize(emptyCard);
            return new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent(emptyJson, Encoding.UTF8, "application/json")
            };
        }
    }
}
