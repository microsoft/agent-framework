// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using A2A;

namespace Microsoft.Agents.AI.A2A.UnitTests;

/// <summary>
/// Unit tests for the <see cref="A2AAgentCardExtensions"/> class.
/// </summary>
public sealed class A2AAgentCardExtensionsTests
{
    private readonly AgentCard _agentCard;

    public A2AAgentCardExtensionsTests()
    {
        this._agentCard = new AgentCard
        {
            Name = "Test Agent",
            Description = "A test agent for unit testing",
            SupportedInterfaces = [new AgentInterface { Url = "http://test-endpoint/agent" }]
        };
    }

    [Fact]
    public void GetAIAgent_ReturnsAIAgent()
    {
        // Act
        var agent = this._agentCard.AsAIAgent();

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<A2AAgent>(agent);
        Assert.Equal("Test Agent", agent.Name);
        Assert.Equal("A test agent for unit testing", agent.Description);
    }

    [Fact]
    public async Task RunIAgentAsync_SendsRequestToTheUrlSpecifiedInAgentCardAsync()
    {
        // Arrange
        using var handler = new HttpMessageHandlerStub();
        using var httpClient = new HttpClient(handler, false);

        handler.ResponsesToReturn.Enqueue(new Message
        {
            Role = Role.Agent,
            Parts = [Part.FromText("Response")],
        });

        var agent = this._agentCard.AsAIAgent(httpClient);

        // Act
        await agent.RunAsync("Test input");

        // Assert
        Assert.Single(handler.CapturedUris);
        Assert.Equal(new Uri("http://test-endpoint/agent"), handler.CapturedUris[0]);
    }

    [Fact]
    public async Task AsAIAgent_WithInterfaceSelector_UsesSelectedInterfaceAsync()
    {
        // Arrange
        var card = new AgentCard
        {
            Name = "Multi-Interface Agent",
            Description = "An agent with multiple interfaces",
            SupportedInterfaces =
            [
                new AgentInterface { Url = "http://first/agent" },
                new AgentInterface { Url = "http://second/agent", ProtocolBinding = "grpc" },
                new AgentInterface { Url = "http://third/agent", ProtocolBinding = "http" },
            ]
        };

        using var handler = new HttpMessageHandlerStub();
        using var httpClient = new HttpClient(handler, false);

        handler.ResponsesToReturn.Enqueue(new Message
        {
            Role = Role.Agent,
            Parts = [Part.FromText("Response")],
        });

        var agent = card.AsAIAgent(httpClient, interfaceSelector: interfaces =>
            interfaces.First(i => i.ProtocolBinding == "http"));

        // Act
        await agent.RunAsync("Test input");

        // Assert
        Assert.Single(handler.CapturedUris);
        Assert.Equal(new Uri("http://third/agent"), handler.CapturedUris[0]);
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
                var sendMessageResponse = new SendMessageResponse { Message = message };
                var jsonRpcResponse = new JsonRpcResponse
                {
                    Id = "response-id",
                    Result = JsonSerializer.SerializeToNode(sendMessageResponse, A2AJsonUtilities.DefaultOptions)
                };

                return new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new StringContent(JsonSerializer.Serialize(jsonRpcResponse, A2AJsonUtilities.DefaultOptions), Encoding.UTF8, "application/json")
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
