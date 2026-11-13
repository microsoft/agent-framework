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

namespace Microsoft.Agents.AI.A2A.UnitTests;

/// <summary>
/// Unit tests for the <see cref="AgentCardExtensions"/> class.
/// </summary>
public sealed class AgentCardExtensionsTests
{
    private readonly AgentCard _agentCard;

    public AgentCardExtensionsTests()
    {
        this._agentCard = new AgentCard
        {
            Name = "Test Agent",
            Description = "A test agent for unit testing",
            SupportedInterfaces = [new AgentInterface { Url = "https://test-endpoint/agent" }]
        };
    }

    [Fact]
    public void AsAIAgent_ReturnsA2AAgent()
    {
        // Act
        A2AAgent agent = this._agentCard.AsAIAgent();

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

        var agent = this._agentCard.AsAIAgent(httpClient: httpClient);

        // Act
        await agent.RunAsync("Test input");

        // Assert
        Assert.Single(handler.CapturedUris);
        Assert.Equal(new Uri("https://test-endpoint/agent"), handler.CapturedUris[0]);
    }

    [Fact]
    public async Task AsAIAgent_WithPreferredBindings_UsesMatchingInterfaceAsync()
    {
        // Arrange
        var card = new AgentCard
        {
            Name = "Multi-Interface Agent",
            Description = "An agent with multiple interfaces",
            SupportedInterfaces =
            [
                new AgentInterface { Url = "https://first/agent", ProtocolBinding = ProtocolBindingNames.HttpJson },
                new AgentInterface { Url = "https://second/agent", ProtocolBinding = ProtocolBindingNames.JsonRpc },
            ]
        };

        using var handler = new HttpMessageHandlerStub();
        using var httpClient = new HttpClient(handler, false);

        handler.ResponsesToReturn.Enqueue(new Message
        {
            Role = Role.Agent,
            Parts = [Part.FromText("Response")],
        });

        var options = new A2AClientOptions
        {
            PreferredBindings = [ProtocolBindingNames.JsonRpc]
        };

        var agent = card.AsAIAgent(httpClient, options: options);

        // Act
        await agent.RunAsync("Test input");

        // Assert
        Assert.Single(handler.CapturedUris);
        Assert.Equal(new Uri("https://second/agent"), handler.CapturedUris[0]);
    }

    [Fact]
    public void AsAIAgent_WithNullOptions_UsesDefaultBindingPreference()
    {
        // Arrange
        var card = new AgentCard
        {
            Name = "Default Options Agent",
            Description = "Tests default A2AClientOptions behavior",
            SupportedInterfaces =
            [
                new AgentInterface { Url = "https://default/agent" },
            ]
        };

        // Act - null options should use defaults (HTTP+JSON first, JSON-RPC as fallback)
        var agent = card.AsAIAgent(options: null);

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<A2AAgent>(agent);
        Assert.Equal("Default Options Agent", agent.Name);
    }

    [Fact]
    public void AsAIAgent_WithNoMatchingBinding_ThrowsException()
    {
        // Arrange
        var card = new AgentCard
        {
            Name = "Unmatched Binding Agent",
            Description = "Agent with unsupported binding only",
            SupportedInterfaces =
            [
                new AgentInterface { Url = "https://grpc/agent", ProtocolBinding = "GRPC" },
            ]
        };

        var options = new A2AClientOptions
        {
            PreferredBindings = [ProtocolBindingNames.JsonRpc]
        };

        // Act & Assert - factory should throw when no matching binding exists
        Assert.ThrowsAny<Exception>(() => card.AsAIAgent(options: options));
    }

    [Fact]
    public void AsAIAgent_WithNoSupportedInterfaces_ThrowsException()
    {
        // Arrange
        var card = new AgentCard
        {
            Name = "No Interfaces Agent",
            Description = "Agent with no supported interfaces",
        };

        // Act & Assert
        Assert.ThrowsAny<Exception>(() => card.AsAIAgent());
    }

    [Fact]
    public void AsAIAgent_WithAgentOptions_OverridesCardValues()
    {
        // Arrange
        var card = new AgentCard
        {
            Name = "Card Agent",
            Description = "Card description",
            SupportedInterfaces = [new AgentInterface { Url = "https://test-endpoint/agent" }]
        };

        var agentOptions = new A2AAgentOptions
        {
            Id = "custom-id",
            Name = "Custom Agent",
            Description = "Custom description"
        };

        // Act
        A2AAgent agent = card.AsAIAgent(agentOptions);

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<A2AAgent>(agent);
        Assert.Equal("custom-id", agent.Id);
        Assert.Equal("Custom Agent", agent.Name);
        Assert.Equal("Custom description", agent.Description);
    }

    [Fact]
    public void AsAIAgent_WithAgentOptions_FallsBackToCardValues()
    {
        // Arrange
        var card = new AgentCard
        {
            Name = "Card Agent",
            Description = "Card description",
            SupportedInterfaces = [new AgentInterface { Url = "https://test-endpoint/agent" }]
        };

        var agentOptions = new A2AAgentOptions
        {
            Id = "custom-id"
        };

        // Act
        var agent = card.AsAIAgent(agentOptions);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("custom-id", agent.Id);
        Assert.Equal("Card Agent", agent.Name);
        Assert.Equal("Card description", agent.Description);
    }

    [Fact]
    public void AsAIAgent_WithEmptyAgentOptions_UsesCardValues()
    {
        // Arrange
        var card = new AgentCard
        {
            Name = "Card Agent",
            Description = "Card description",
            SupportedInterfaces = [new AgentInterface { Url = "https://test-endpoint/agent" }]
        };

        // Act
        var agent = card.AsAIAgent(new A2AAgentOptions());

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("Card Agent", agent.Name);
        Assert.Equal("Card description", agent.Description);
    }

    [Theory]
    [InlineData("http://test-endpoint/agent", false, null)]
    [InlineData("/relative/agent", true, null)]
    [InlineData("ftp://test-endpoint/agent", true, null)]
    [InlineData("https://other-host/agent", false, "test-endpoint")]
    [InlineData("https://test-endpoint.other-host/agent", false, "test-endpoint")]
    [InlineData("https://test-endpoint:8443/agent", false, "test-endpoint:443")]
    public void AsAIAgent_WithOnlyDisallowedAddresses_ThrowsInvalidOperationException(string url, bool allowInsecureHttp, string? allowedHost)
    {
        // Arrange
        var card = new AgentCard
        {
            Name = "Card Agent",
            SupportedInterfaces = [new AgentInterface { Url = url }]
        };

        var agentOptions = new A2AAgentOptions
        {
            AllowAgentCardHostsInsecureHttp = allowInsecureHttp,
            AgentCardAllowedHosts = allowedHost is null ? null : [allowedHost]
        };

        // Act & Assert
        Assert.Throws<InvalidOperationException>(() => card.AsAIAgent(agentOptions));
    }

    [Fact]
    public void AsAIAgent_WithEmptyAgentCardAllowedHosts_ThrowsInvalidOperationException()
    {
        // Arrange
        var agentOptions = new A2AAgentOptions { AgentCardAllowedHosts = [] };

        // Act & Assert
        Assert.Throws<InvalidOperationException>(() => this._agentCard.AsAIAgent(agentOptions));
    }

    [Theory]
    [InlineData("https://test-endpoint")]
    [InlineData("*.test-endpoint")]
    [InlineData("test-endpoint:99999")]
    [InlineData("test-endpoint/agent")]
    public void AsAIAgent_WithInvalidAgentCardAllowedHostsEntry_ThrowsArgumentException(string allowedHost)
    {
        // Arrange
        var agentOptions = new A2AAgentOptions { AgentCardAllowedHosts = [allowedHost] };

        // Act & Assert
        Assert.Throws<ArgumentException>(() => this._agentCard.AsAIAgent(agentOptions));
    }

    [Theory]
    [InlineData("https://trusted-host:8443/agent", "trusted-host", false)]
    [InlineData("https://trusted-host:8443/agent", "trusted-host:8443", false)]
    [InlineData("http://trusted-host/agent", "trusted-host", true)]
    [InlineData("http://trusted-host:5000/agent", "trusted-host:5000", true)]
    public async Task AsAIAgent_WithAllowedHostAndPort_SendsRequestToAddressAsync(string url, string allowedHost, bool allowInsecureHttp)
    {
        // Arrange
        using var handler = new HttpMessageHandlerStub();
        using var httpClient = new HttpClient(handler, false);

        handler.ResponsesToReturn.Enqueue(new Message
        {
            Role = Role.Agent,
            Parts = [Part.FromText("Response")],
        });

        var card = new AgentCard
        {
            Name = "Card Agent",
            SupportedInterfaces = [new AgentInterface { Url = url }]
        };

        var agentOptions = new A2AAgentOptions
        {
            AgentCardAllowedHosts = [allowedHost],
            AllowAgentCardHostsInsecureHttp = allowInsecureHttp
        };

        var agent = card.AsAIAgent(agentOptions, httpClient);

        // Act
        await agent.RunAsync("Test input");

        // Assert
        Assert.Equal(new Uri(url), Assert.Single(handler.CapturedUris));
    }

    [Fact]
    public async Task AsAIAgent_WithAllowAgentCardHostsInsecureHttp_SendsRequestToHttpAddressAsync()
    {
        // Arrange
        using var handler = new HttpMessageHandlerStub();
        using var httpClient = new HttpClient(handler, false);

        handler.ResponsesToReturn.Enqueue(new Message
        {
            Role = Role.Agent,
            Parts = [Part.FromText("Response")],
        });

        var card = new AgentCard
        {
            Name = "Card Agent",
            SupportedInterfaces = [new AgentInterface { Url = "http://test-endpoint/agent" }]
        };

        var agent = card.AsAIAgent(new A2AAgentOptions { AllowAgentCardHostsInsecureHttp = true }, httpClient);

        // Act
        await agent.RunAsync("Test input");

        // Assert
        Assert.Equal(new Uri("http://test-endpoint/agent"), Assert.Single(handler.CapturedUris));
    }

    [Fact]
    public async Task AsAIAgent_WithMixedAddresses_SkipsDisallowedAddressesAsync()
    {
        // Arrange
        using var handler = new HttpMessageHandlerStub();
        using var httpClient = new HttpClient(handler, false);

        handler.ResponsesToReturn.Enqueue(new Message
        {
            Role = Role.Agent,
            Parts = [Part.FromText("Response")],
        });

        var card = new AgentCard
        {
            Name = "Card Agent",
            SupportedInterfaces =
            [
                new AgentInterface { Url = "http://trusted-host/agent" },
                new AgentInterface { Url = "https://other-host/agent" },
                new AgentInterface { Url = "https://Trusted-Host/agent" },
            ]
        };

        var agent = card.AsAIAgent(new A2AAgentOptions { AgentCardAllowedHosts = ["trusted-host"] }, httpClient);

        // Act
        await agent.RunAsync("Test input");

        // Assert
        Assert.Equal(new Uri("https://trusted-host/agent"), Assert.Single(handler.CapturedUris));
        Assert.Equal(3, card.SupportedInterfaces.Count);
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
