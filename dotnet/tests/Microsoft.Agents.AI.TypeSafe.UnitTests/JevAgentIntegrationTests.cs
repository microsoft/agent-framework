// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel;
using System.ClientModel.Primitives;
using System.Collections.Generic;
using System.Linq;
using System.Net.Http;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;

namespace Microsoft.Agents.AI.TypeSafe.UnitTests;

public sealed class JevAgentIntegrationTests
{
    [Fact]
    public async Task RunAsync_AgentCallsTheTool_ModelReceivesTheAnswersAsync()
    {
        // Arrange
        using var handler = new JevTestHttpHandler();
        using var httpClient = new HttpClient(handler);
        AIFunction jev = new JevAIToolBuilder(
            new ApiKeyCredential("test-key"),
            new JevAIToolOptions { Transport = new HttpClientPipelineTransport(httpClient) }).Build();

        using var model = new ScriptedChatClient(
            _ => new ChatResponse(new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("call_1", jev.Name, JevTestData.CallArguments(JevTestData.RequestJson))])),
            _ => new ChatResponse(new ChatMessage(ChatRole.Assistant, "Routed to the technical team as urgent.")));
        AIAgent agent = model.AsAIAgent(instructions: "Triage support tickets with the Jev tool.", tools: [jev]);

        // Act
        AgentResponse response = await agent.RunAsync(JevTestData.TicketText);

        // Assert
        Assert.Equal("Routed to the technical team as urgent.", response.Text);
        Assert.Single(handler.Requests);

        FunctionResultContent result = model.Calls[1].SelectMany(static m => m.Contents).OfType<FunctionResultContent>().Single();
        Assert.Null(result.Exception);

        // Chat clients serialize tool results with AIJsonUtilities.DefaultOptions before sending them to the model.
        string sent = JsonSerializer.Serialize(result.Result, AIJsonUtilities.DefaultOptions.GetTypeInfo(typeof(object)));
        Assert.True(JsonNode.DeepEquals(JsonNode.Parse(JevTestData.ResponseJson), JsonNode.Parse(sent)), sent);
    }

    [Fact]
    public async Task GetResponseAsync_InvalidArgumentsWithDetailedErrors_TellTheModelWhatToFixAsync()
    {
        // Arrange
        AIFunction jev = new JevAIToolBuilder().UseMapping((_, _, _) => Task.FromResult(JevTestData.CreateResult())).Build();
        const string InvalidArguments = """{"state":"x","questions":{"q":{"type":"score","instructions":"How bad?","criteria":["only"]}}}""";

        using var model = new ScriptedChatClient(
            _ => new ChatResponse(new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("call_1", jev.Name, JevTestData.CallArguments(InvalidArguments))])),
            _ => new ChatResponse(new ChatMessage(ChatRole.Assistant, "done")));
        using var client = new FunctionInvokingChatClient(model) { IncludeDetailedErrors = true };

        // Act
        await client.GetResponseAsync("How bad is it?", new ChatOptions { Tools = [jev] });

        // Assert
        FunctionResultContent result = model.Calls[1].SelectMany(static m => m.Contents).OfType<FunctionResultContent>().Single();
        Assert.Contains("has 1 criterion; it needs from 2 to 10", result.Result?.ToString(), StringComparison.Ordinal);
    }

    [Fact]
    public async Task RunAsync_AgentWithServices_ToolResolvesTheClientFromThemAsync()
    {
        // Arrange
        var classifier = new UrgencyClassifier(probability: 0.93);
        using ServiceProvider services = new ServiceCollection().AddSingleton(classifier).BuildServiceProvider();

        AIFunction jev = new JevAIToolBuilder()
            .UseClient<UrgencyClassifier, string, double>(
                static (client, text, cancellationToken) => client.ScoreAsync(text, cancellationToken),
                inputMapper: static request => request.State.Text!,
                outputMapper: static probability => new JevResult
                {
                    Model = "urgency-classifier",
                    Answers = new Dictionary<string, JevResponse> { ["is_urgent"] = new JevNoulResponse { Noul = probability } },
                    Usage = new JevUsage { InputTokens = 0, OutputTokens = 0 },
                })
            .Build();

        const string Arguments = """{"state":"Please help ASAP","questions":{"is_urgent":{"type":"noul","instructions":"Is this urgent?"}}}""";
        using var model = new ScriptedChatClient(
            _ => new ChatResponse(new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("call_1", jev.Name, JevTestData.CallArguments(Arguments))])),
            _ => new ChatResponse(new ChatMessage(ChatRole.Assistant, "Urgent.")));
        AIAgent agent = model.AsAIAgent(tools: [jev], services: services);

        // Act
        AgentResponse response = await agent.RunAsync("Please help ASAP");

        // Assert
        Assert.Equal("Urgent.", response.Text);
        Assert.Equal("Please help ASAP", classifier.Received);
        FunctionResultContent result = model.Calls[1].SelectMany(static m => m.Contents).OfType<FunctionResultContent>().Single();
        Assert.Equal(0.93, Assert.IsType<JsonElement>(result.Result).GetProperty("answers").GetProperty("is_urgent").GetProperty("noul").GetDouble());
    }

    /// <summary>A hypothetical third-party client registered in the application's services.</summary>
    private sealed class UrgencyClassifier(double probability)
    {
        public string? Received { get; private set; }

        public Task<double> ScoreAsync(string text, CancellationToken cancellationToken)
        {
            this.Received = text;
            return Task.FromResult(probability);
        }
    }
}
