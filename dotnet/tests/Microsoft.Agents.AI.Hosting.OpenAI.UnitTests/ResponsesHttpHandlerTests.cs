// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.OpenAI.Tests;
using Microsoft.Agents.AI.Workflows;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Moq;
using static Microsoft.Agents.AI.Hosting.OpenAI.UnitTests.TestHelpers;

namespace Microsoft.Agents.AI.Hosting.OpenAI.UnitTests;

/// <summary>
/// Tests for approval requests passing through the Responses HTTP handler.
/// </summary>
public sealed class ResponsesHttpHandlerTests : ConformanceTestBase
{
    private static readonly bool[] s_booleanValues = [true, false];

    public static IEnumerable<object[]> ApprovalScenarios =>
        from approved in s_booleanValues
        from stream in s_booleanValues
        from resolveAgent in s_booleanValues
        from workflow in s_booleanValues
        from conversation in s_booleanValues
        select new object[] { approved, stream, resolveAgent, workflow, conversation };

    [Theory]
    [MemberData(nameof(ApprovalScenarios))]
    public async Task CreateResponseAsync_FunctionApproval_RestoresSessionAndInvokesToolOnlyWhenApprovedAsync(
        bool approved, bool stream, bool resolveAgent, bool workflow, bool conversation)
    {
        // Arrange
        List<string> toolInvocations = [];
        AIFunction tool = new ApprovalRequiredAIFunction(AIFunctionFactory.Create((string location) =>
        {
            toolInvocations.Add(location);
            return "Sunny";
        }, "get_weather"));
        int modelCalls = 0;
        List<ChatMessage>? resumedMessages = null;
        Mock<IChatClient> chatClient = new();
        chatClient.Setup(c => c.GetStreamingResponseAsync(
            It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions?>(), It.IsAny<CancellationToken>()))
            .Returns((IEnumerable<ChatMessage> messages, ChatOptions? _, CancellationToken _) =>
            {
                resumedMessages = messages.ToList();
                AIContent content = ++modelCalls == 1
                    ? new FunctionCallContent("call-1", "get_weather", new Dictionary<string, object?> { ["location"] = "Seattle" })
                    : new TextContent("Decision processed");
                return new ChatResponse([new ChatMessage(ChatRole.Assistant, [content])]).ToChatResponseUpdates().ToAsyncEnumerable();
            });
        AIAgent agent = new ChatClientAgent(chatClient.Object, name: "approval-agent", tools: [tool]);
        if (workflow)
        {
            agent = new WorkflowBuilder(agent.BindAsExecutor(new AIAgentHostOptions { EmitAgentUpdateEvents = true }))
                .Build().AsAIAgent(name: "approval-agent");
        }

        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        builder.WebHost.UseTestServer();
        builder.AddAIAgent("approval-agent", (_, _) => agent).WithInMemorySessionStore(withIsolation: false);
        builder.AddOpenAIResponses();
        builder.AddOpenAIConversations();
        await using WebApplication app = builder.Build();
        app.MapOpenAIConversations();
        if (resolveAgent)
        {
            app.MapOpenAIResponses();
        }
        else
        {
            app.MapOpenAIResponses(agent, "/v1/responses");
        }

        await app.StartAsync();
        using HttpClient client = app.GetTestClient();
        string? conversationId = null;
        if (conversation)
        {
            using StringContent createConversationContent = new("{}", Encoding.UTF8, "application/json");
            using HttpResponseMessage conversationResponse = await client.PostAsync(new Uri("/v1/conversations", UriKind.Relative), createConversationContent);
            conversationResponse.EnsureSuccessStatusCode();
            using JsonDocument conversationDocument = JsonDocument.Parse(await conversationResponse.Content.ReadAsStringAsync());
            conversationId = conversationDocument.RootElement.GetProperty("id").GetString();
        }

        using StringContent initialContent = new(
            $$"""{"agent":{"name":"approval-agent"},"input":"What is the weather?","stream":true,"conversation":{{JsonSerializer.Serialize(conversationId)}}}""",
            Encoding.UTF8, "application/json");
        using HttpResponseMessage initialResponse = await client.PostAsync(new Uri("/v1/responses", UriKind.Relative), initialContent);
        Assert.Equal(HttpStatusCode.OK, initialResponse.StatusCode);
        List<JsonElement> initialEvents = ParseSseEvents(await initialResponse.Content.ReadAsStringAsync());
        JsonElement approvalEvent = Assert.Single(initialEvents,
            e => e.GetProperty("type").GetString() == "response.function_approval.requested");
        string? responseId = initialEvents.Last().GetProperty("response").GetProperty("id").GetString();
        string continuation = conversation
            ? $""" "conversation": {JsonSerializer.Serialize(conversationId)} """
            : $""" "previous_response_id": {JsonSerializer.Serialize(responseId)} """;
        Assert.Empty(toolInvocations);
        if (workflow)
        {
            Assert.Contains(":", approvalEvent.GetProperty("request_id").GetString(), StringComparison.Ordinal);
        }

        string approvalJson = $$"""
            {
              "agent": { "name": "approval-agent" },
              {{continuation}},
              "stream": {{(stream ? "true" : "false")}},
              "input": [{
                "type": "message",
                "role": "user",
                "content": [{
                  "type": "function_approval_response",
                  "request_id": {{approvalEvent.GetProperty("request_id").GetRawText()}},
                  "approved": {{(approved ? "true" : "false")}},
                  "function_call": {{approvalEvent.GetProperty("function_call").GetRawText()}}
                }]
              }]
            }
            """;
        using StringContent approvalContent = new(approvalJson, Encoding.UTF8, "application/json");

        // Act
        using HttpResponseMessage response = await client.PostAsync(new Uri("/v1/responses", UriKind.Relative), approvalContent);
        string body = await response.Content.ReadAsStringAsync();

        // Assert
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.Equal(2, modelCalls);
        Assert.Equal(approved ? ["Seattle"] : Array.Empty<string>(), toolInvocations);
        Assert.NotNull(resumedMessages);
        Assert.Contains(resumedMessages.SelectMany(m => m.Contents),
            c => c is FunctionResultContent { CallId: "call-1" });
        Assert.Contains("Decision processed", body, StringComparison.Ordinal);
        if (stream)
        {
            List<JsonElement> events = ParseSseEvents(body);
            Assert.Contains(events, e => e.GetProperty("type").GetString() == "response.completed");
            Assert.DoesNotContain(events, e => e.GetProperty("type").GetString() == "response.function_approval.requested");
        }
        else
        {
            using JsonDocument document = JsonDocument.Parse(body);
            Assert.Equal("completed", document.RootElement.GetProperty("status").GetString());
        }
    }

    [Theory]
    [InlineData("""{"request_id":"request-1","function_call":{"id":"call-1","name":"tool","arguments":{}}}""")]
    [InlineData("""{"approved":true,"function_call":{"id":"call-1","name":"tool","arguments":{}}}""")]
    [InlineData("""{"request_id":"request-1","approved":true}""")]
    [InlineData("""{"request_id":null,"approved":true,"function_call":{"id":"call-1","name":"tool","arguments":{}}}""")]
    [InlineData("""{"request_id":"request-1","approved":true,"function_call":null}""")]
    [InlineData("""{"request_id":"request-1","approved":true,"function_call":{"id":null,"name":"tool","arguments":{}}}""")]
    [InlineData("""{"request_id":"request-1","approved":true,"function_call":{"id":"call-1","name":null,"arguments":{}}}""")]
    [InlineData("""{"request_id":"request-1","approved":true,"function_call":{"id":"call-1","name":"tool","arguments":[]}}""")]
    [InlineData("""{"request_id":"request-1","approved":true,"function_call":{"id":"call-1","name":"tool","arguments":"{}"}}""")]
    public async Task CreateResponseAsync_InvalidFunctionApproval_ReturnsBadRequestAsync(string fields)
    {
        // Arrange
        HttpClient client = await this.CreateTestServerAsync("approval-agent", "Test agent", "Should not run");
        string json = $$"""
            {"input":[{"role":"user","content":[{"type":"function_approval_response",{{fields[1..]}}]}]}
            """;
        using StringContent content = new(json, Encoding.UTF8, "application/json");

        // Act
        using HttpResponseMessage response = await client.PostAsync(new Uri("/approval-agent/v1/responses", UriKind.Relative), content);

        // Assert
        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
    }
}
