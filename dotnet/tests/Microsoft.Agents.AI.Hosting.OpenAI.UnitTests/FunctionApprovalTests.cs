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

namespace Microsoft.Agents.AI.Hosting.OpenAI.UnitTests;

/// <summary>
/// Tests for function approval request and response content types.
/// These are DevUI-specific extensions that allow approval workflows for function calls.
/// </summary>
public sealed class FunctionApprovalTests : ConformanceTestBase
{
    private static readonly bool[] s_booleanValues = [false, true];

    // Streaming request JSON for OpenAI Responses API
    private const string StreamingRequestJson = @"{""model"":""gpt-4o-mini"",""input"":""test"",""stream"":true}";

    public static IEnumerable<object[]> ApprovalContinuationScenarios =>
        from resolveAgent in s_booleanValues
        from useConversation in s_booleanValues
        from approved in s_booleanValues
        from stream in s_booleanValues
        from useWorkflow in s_booleanValues
        select new object[] { resolveAgent, useConversation, approved, stream, useWorkflow };

    #region ToolApprovalRequestContent Tests

    [Fact]
    public async Task FunctionApprovalRequest_GeneratesCorrectEvent_SuccessAsync()
    {
        // Arrange
        const string AgentName = "approval-request-agent";
        const string RequestId = "req-123";
        const string FunctionName = "get_weather";
        const string FunctionId = "call-abc123";
        Dictionary<string, object?> arguments = new() { ["location"] = "Seattle", ["unit"] = "celsius" };

#pragma warning disable MEAI001 // Type is for evaluation purposes only and is subject to change or removal in future updates
        FunctionCallContent functionCall = new(FunctionId, FunctionName, arguments);
        ToolApprovalRequestContent approvalRequest = new(RequestId, functionCall);
#pragma warning restore MEAI001

        HttpClient client = await this.CreateTestServerAsync(AgentName, "You are a test agent.", string.Empty, (msg) =>
            [approvalRequest]);

        // Act
        HttpResponseMessage httpResponse = await this.SendResponsesRequestAsync(client, AgentName, StreamingRequestJson);
        string sseContent = await httpResponse.Content.ReadAsStringAsync();
        List<JsonElement> events = ParseSseEvents(sseContent);

        // Assert
        Assert.NotEmpty(events);

        // Verify function approval requested event
        JsonElement approvalEvent = events.FirstOrDefault(e =>
            e.GetProperty("type").GetString() == "response.function_approval.requested");
        Assert.True(approvalEvent.ValueKind != JsonValueKind.Undefined, "approval event not found");

        Assert.Equal(RequestId, approvalEvent.GetProperty("request_id").GetString());

        JsonElement functionCallElement = approvalEvent.GetProperty("function_call");
        Assert.Equal(FunctionId, functionCallElement.GetProperty("id").GetString());
        Assert.Equal(FunctionName, functionCallElement.GetProperty("name").GetString());

        JsonElement argumentsElement = functionCallElement.GetProperty("arguments");
        Assert.Equal("Seattle", argumentsElement.GetProperty("location").GetString());
        Assert.Equal("celsius", argumentsElement.GetProperty("unit").GetString());
    }

    [Fact]
    public async Task FunctionApprovalRequest_WithComplexArguments_GeneratesCorrectEvent_SuccessAsync()
    {
        // Arrange
        const string AgentName = "approval-request-complex-args-agent";
        const string RequestId = "req-456";
        const string FunctionName = "calculate";
        const string FunctionId = "call-def456";
        Dictionary<string, object?> arguments = new()
        {
            ["expression"] = "2+2",
            ["precision"] = 2,
            ["options"] = new Dictionary<string, object?> { ["decimal"] = true }
        };

#pragma warning disable MEAI001 // Type is for evaluation purposes only and is subject to change or removal in future updates
        FunctionCallContent functionCall = new(FunctionId, FunctionName, arguments);
        ToolApprovalRequestContent approvalRequest = new(RequestId, functionCall);
#pragma warning restore MEAI001

        HttpClient client = await this.CreateTestServerAsync(AgentName, "You are a test agent.", string.Empty, (msg) =>
            [approvalRequest]);

        // Act
        HttpResponseMessage httpResponse = await this.SendResponsesRequestAsync(client, AgentName, StreamingRequestJson);
        string sseContent = await httpResponse.Content.ReadAsStringAsync();
        List<JsonElement> events = ParseSseEvents(sseContent);

        // Assert
        JsonElement approvalEvent = events.FirstOrDefault(e =>
            e.GetProperty("type").GetString() == "response.function_approval.requested");
        Assert.NotEqual(JsonValueKind.Undefined, approvalEvent.ValueKind);

        JsonElement functionCallElement = approvalEvent.GetProperty("function_call");
        JsonElement argumentsElement = functionCallElement.GetProperty("arguments");

        // Verify complex arguments are serialized correctly
        Assert.Equal("2+2", argumentsElement.GetProperty("expression").GetString());
        Assert.Equal(2, argumentsElement.GetProperty("precision").GetInt32());
        Assert.True(argumentsElement.GetProperty("options").GetProperty("decimal").GetBoolean());
    }

    [Fact]
    public async Task FunctionApprovalRequest_WithoutArguments_EmitsEmptyArgumentsObjectAsync()
    {
        // Arrange
        const string AgentName = "approval-request-no-args-agent";
        ToolApprovalRequestContent approvalRequest = new(
            "request-1",
            new FunctionCallContent("call-1", "get_time"));
        HttpClient client = await this.CreateTestServerAsync(
            AgentName,
            "You are a test agent.",
            string.Empty,
            _ => [approvalRequest]);

        // Act
        using HttpResponseMessage response = await this.SendResponsesRequestAsync(
            client,
            AgentName,
            StreamingRequestJson);
        List<JsonElement> events = ParseSseEvents(await response.Content.ReadAsStringAsync());

        // Assert
        JsonElement approvalEvent = Assert.Single(events,
            item => item.GetProperty("type").GetString() == "response.function_approval.requested");
        JsonElement arguments = approvalEvent.GetProperty("function_call").GetProperty("arguments");
        Assert.Equal(JsonValueKind.Object, arguments.ValueKind);
        Assert.Empty(arguments.EnumerateObject());
    }

    [Fact]
    public async Task FunctionApprovalRequest_EmitsCorrectEventSequence_SuccessAsync()
    {
        // Arrange
        const string AgentName = "approval-sequence-agent";

#pragma warning disable MEAI001 // Type is for evaluation purposes only and is subject to change or removal in future updates
        FunctionCallContent functionCall = new("call-1", "test_function", new Dictionary<string, object?>());
        ToolApprovalRequestContent approvalRequest = new("req-1", functionCall);
#pragma warning restore MEAI001

        HttpClient client = await this.CreateTestServerAsync(AgentName, "You are a test agent.", string.Empty, (msg) =>
            [approvalRequest]);

        // Act
        HttpResponseMessage httpResponse = await this.SendResponsesRequestAsync(client, AgentName, StreamingRequestJson);
        string sseContent = await httpResponse.Content.ReadAsStringAsync();
        List<JsonElement> events = ParseSseEvents(sseContent);

        // Assert - Verify event sequence
        List<string?> eventTypes = events.ConvertAll(e => e.GetProperty("type").GetString());

        Assert.Equal("response.created", eventTypes[0]);
        Assert.Equal("response.in_progress", eventTypes[1]);
        Assert.Contains("response.function_approval.requested", eventTypes);
        Assert.Contains("response.completed", eventTypes);

        // Approval request should come after in_progress and before completed
        int approvalIndex = eventTypes.IndexOf("response.function_approval.requested");
        int inProgressIndex = eventTypes.IndexOf("response.in_progress");
        int completedIndex = eventTypes.IndexOf("response.completed");

        Assert.True(approvalIndex > inProgressIndex);
        Assert.True(approvalIndex < completedIndex);
    }

    [Fact]
    public async Task FunctionApprovalRequest_SequenceNumbersAreCorrect_SuccessAsync()
    {
        // Arrange
        const string AgentName = "approval-seq-num-agent";

#pragma warning disable MEAI001 // Type is for evaluation purposes only and is subject to change or removal in future updates
        FunctionCallContent functionCall = new("call-1", "test", new Dictionary<string, object?>());
        ToolApprovalRequestContent approvalRequest = new("req-1", functionCall);
#pragma warning restore MEAI001

        HttpClient client = await this.CreateTestServerAsync(AgentName, "You are a test agent.", string.Empty, (msg) =>
            [approvalRequest]);

        // Act
        HttpResponseMessage httpResponse = await this.SendResponsesRequestAsync(client, AgentName, StreamingRequestJson);
        string sseContent = await httpResponse.Content.ReadAsStringAsync();
        List<JsonElement> events = ParseSseEvents(sseContent);

        // Assert - Sequence numbers are sequential
        List<int> sequenceNumbers = events.ConvertAll(e => e.GetProperty("sequence_number").GetInt32());
        Assert.NotEmpty(sequenceNumbers);

        for (int i = 0; i < sequenceNumbers.Count; i++)
        {
            Assert.Equal(i, sequenceNumbers[i]);
        }
    }

    #endregion

    #region ToolApprovalResponseContent Tests

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task FunctionApprovalResponse_WithoutSessionStore_ReturnsBadRequestAsync(bool resolveAgent)
    {
        // Arrange
        const string AgentName = "approval-response-input-agent";
        AIAgent agent = new ChatClientAgent(new TestHelpers.SimpleMockChatClient(), name: AgentName);
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        builder.WebHost.UseTestServer();
        builder.AddAIAgent(AgentName, (_, _) => agent);
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
        var responsesUri = new Uri(resolveAgent ? "/v1/responses" : $"/{AgentName}/v1/responses", UriKind.Relative);
        string requestJson = $$"""
            {
              "agent": { "name": "{{AgentName}}" },
              "input": [{
                "type": "message",
                "role": "user",
                "content": [{
                  "type": "function_approval_response",
                  "request_id": "request-1",
                  "approved": true,
                  "function_call": {
                    "id": "call-1",
                    "name": "get_weather",
                    "arguments": { "location": "Seattle" }
                  }
                }]
              }]
            }
            """;
        using StringContent content = new(requestJson, Encoding.UTF8, "application/json");

        // Act
        using HttpResponseMessage response = await client.PostAsync(responsesUri, content);
        string responseBody = await response.Content.ReadAsStringAsync();

        // Assert
        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
        Assert.Contains(
            "Approval-required function calling is not supported because no AgentSessionStore is configured.",
            responseBody,
            StringComparison.Ordinal);
    }

    [Theory]
    [InlineData(false, false)]
    [InlineData(false, true)]
    [InlineData(true, false)]
    [InlineData(true, true)]
    public async Task FunctionApprovalResponse_UnknownOrCrossSessionRequestId_ReturnsBadRequestBeforeExecutionAsync(
        bool resolveAgent,
        bool useCrossSessionRequestId)
    {
        // Arrange
        const string AgentName = "unknown-approval-response-agent";
        const string FunctionName = "get_weather";
        int functionInvocations = 0;
        AIFunction function = new ApprovalRequiredAIFunction(AIFunctionFactory.Create(
            () =>
            {
                Interlocked.Increment(ref functionInvocations);
                return "Sunny";
            },
            FunctionName));
        int modelCalls = 0;
        Mock<IChatClient> chatClient = new();
        chatClient
            .Setup(client => client.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions?>(),
                It.IsAny<CancellationToken>()))
            .Returns(() =>
            {
                int call = Interlocked.Increment(ref modelCalls);
                return new ChatResponse([
                    new ChatMessage(ChatRole.Assistant, [
                        new FunctionCallContent($"call-{call}", FunctionName)
                    ])
                ]).ToChatResponseUpdates().ToAsyncEnumerable();
            });
        AIAgent agent = new ChatClientAgent(chatClient.Object, name: AgentName, tools: [function]);

        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        builder.WebHost.UseTestServer();
        builder.AddAIAgent(AgentName, (_, _) => agent)
            .WithInMemorySessionStore(withIsolation: false);
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
        var responsesUri = new Uri(resolveAgent ? "/v1/responses" : $"/{AgentName}/v1/responses", UriKind.Relative);

        using StringContent initialContent = new(
            $$"""{"agent":{"name":"{{AgentName}}"},"input":"What is the weather?","stream":true}""",
            Encoding.UTF8,
            "application/json");
        using HttpResponseMessage initialResponse = await client.PostAsync(responsesUri, initialContent);
        initialResponse.EnsureSuccessStatusCode();
        List<JsonElement> initialEvents = ParseSseEvents(await initialResponse.Content.ReadAsStringAsync());
        JsonElement approvalEvent = Assert.Single(initialEvents,
            item => item.GetProperty("type").GetString() == "response.function_approval.requested");
        string responseId = initialEvents.Last().GetProperty("response").GetProperty("id").GetString()!;
        if (useCrossSessionRequestId)
        {
            using StringContent otherInitialContent = new(
                $$"""{"agent":{"name":"{{AgentName}}"},"input":"What is the weather elsewhere?","stream":true}""",
                Encoding.UTF8,
                "application/json");
            using HttpResponseMessage otherInitialResponse = await client.PostAsync(responsesUri, otherInitialContent);
            otherInitialResponse.EnsureSuccessStatusCode();
            List<JsonElement> otherInitialEvents = ParseSseEvents(await otherInitialResponse.Content.ReadAsStringAsync());
            _ = Assert.Single(otherInitialEvents,
                item => item.GetProperty("type").GetString() == "response.function_approval.requested");
            responseId = otherInitialEvents.Last().GetProperty("response").GetProperty("id").GetString()!;
        }

        string requestId = useCrossSessionRequestId
            ? approvalEvent.GetProperty("request_id").GetRawText()
            : JsonSerializer.Serialize("unknown-request");
        string approvalJson = $$"""
            {
              "agent": { "name": "{{AgentName}}" },
              "previous_response_id": {{JsonSerializer.Serialize(responseId)}},
              "input": [{
                "type": "message",
                "role": "user",
                "content": [{
                  "type": "function_approval_response",
                  "request_id": {{requestId}},
                  "approved": true,
                  "function_call": {{approvalEvent.GetProperty("function_call").GetRawText()}}
                }]
              }]
            }
            """;
        using StringContent approvalContent = new(approvalJson, Encoding.UTF8, "application/json");

        // Act
        using HttpResponseMessage response = await client.PostAsync(responsesUri, approvalContent);
        string responseBody = await response.Content.ReadAsStringAsync();

        // Assert
        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
        Assert.Contains("does not match a pending approval request", responseBody, StringComparison.Ordinal);
        Assert.Equal(0, functionInvocations);
        Assert.Equal(useCrossSessionRequestId ? 2 : 1, modelCalls);
    }

    [Theory]
    [InlineData("missing-approved")]
    [InlineData("array-arguments")]
    [InlineData("string-arguments")]
    [InlineData("number-arguments")]
    [InlineData("boolean-arguments")]
    [InlineData("null-arguments")]
    public async Task FunctionApprovalResponse_InvalidPayload_ReturnsBadRequestBeforeExecutionAsync(string invalidField)
    {
        // Arrange
        const string AgentName = "missing-approved-response-agent";
        const string FunctionName = "get_weather";
        int functionInvocations = 0;
        AIFunction function = new ApprovalRequiredAIFunction(AIFunctionFactory.Create(
            () =>
            {
                Interlocked.Increment(ref functionInvocations);
                return "Sunny";
            },
            FunctionName));
        int modelCalls = 0;
        Mock<IChatClient> chatClient = new();
        chatClient
            .Setup(client => client.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions?>(),
                It.IsAny<CancellationToken>()))
            .Returns(() =>
            {
                AIContent responseContent = Interlocked.Increment(ref modelCalls) == 1
                    ? new FunctionCallContent("call-1", FunctionName)
                    : new TextContent("Decision processed");
                return new ChatResponse([
                    new ChatMessage(ChatRole.Assistant, [responseContent])
                ]).ToChatResponseUpdates().ToAsyncEnumerable();
            });
        AIAgent agent = new ChatClientAgent(chatClient.Object, name: AgentName, tools: [function]);

        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        builder.WebHost.UseTestServer();
        builder.AddAIAgent(AgentName, (_, _) => agent)
            .WithInMemorySessionStore(withIsolation: false);
        builder.AddOpenAIResponses();

        await using WebApplication app = builder.Build();
        app.MapOpenAIResponses(agent);
        await app.StartAsync();
        using HttpClient client = app.GetTestClient();
        var responsesUri = new Uri($"/{AgentName}/v1/responses", UriKind.Relative);

        using StringContent initialContent = new(
            """{"input":"What is the weather?","stream":true}""",
            Encoding.UTF8,
            "application/json");
        using HttpResponseMessage initialResponse = await client.PostAsync(responsesUri, initialContent);
        initialResponse.EnsureSuccessStatusCode();
        List<JsonElement> initialEvents = ParseSseEvents(await initialResponse.Content.ReadAsStringAsync());
        JsonElement approvalEvent = Assert.Single(initialEvents,
            item => item.GetProperty("type").GetString() == "response.function_approval.requested");
        string responseId = initialEvents.Last().GetProperty("response").GetProperty("id").GetString()!;
        string approvedProperty = invalidField == "missing-approved"
            ? string.Empty
            : "\"approved\": true,";
        string argumentsJson = invalidField switch
        {
            "array-arguments" => "[]",
            "string-arguments" => "\"{}\"",
            "number-arguments" => "42",
            "boolean-arguments" => "true",
            "null-arguments" => "null",
            _ => "{}"
        };
        string approvalJson = $$"""
            {
              "previous_response_id": {{JsonSerializer.Serialize(responseId)}},
              "input": [{
                "type": "message",
                "role": "user",
                "content": [{
                  "type": "function_approval_response",
                  "request_id": {{approvalEvent.GetProperty("request_id").GetRawText()}},
                  {{approvedProperty}}
                  "function_call": {
                    "id": "call-1",
                    "name": "{{FunctionName}}",
                    "arguments": {{argumentsJson}}
                  }
                }]
              }]
            }
            """;
        using StringContent approvalContent = new(approvalJson, Encoding.UTF8, "application/json");

        // Act
        using HttpResponseMessage response = await client.PostAsync(responsesUri, approvalContent);

        // Assert
        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
        Assert.Equal(0, functionInvocations);
        Assert.Equal(1, modelCalls);
    }

    [Theory]
    [MemberData(nameof(ApprovalContinuationScenarios))]
    public async Task FunctionApprovalResponse_PendingExecution_ResumesAcrossResponsesAsync(
        bool resolveAgent,
        bool useConversation,
        bool approved,
        bool stream,
        bool useWorkflow)
    {
        // Arrange
        const string AgentName = "approval-workflow-agent";
        const string FunctionName = "get_weather";
        int functionInvocations = 0;
        AIFunction function = new ApprovalRequiredAIFunction(AIFunctionFactory.Create(
            (string location) =>
            {
                Interlocked.Increment(ref functionInvocations);
                return $"Sunny in {location}";
            },
            FunctionName));
        int modelCalls = 0;
        List<ChatMessage>? secondModelMessages = null;
        Mock<IChatClient> chatClient = new();
        chatClient
            .Setup(client => client.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions?>(),
                It.IsAny<CancellationToken>()))
            .Returns((IEnumerable<ChatMessage> messages, ChatOptions? _, CancellationToken _) =>
            {
                int call = Interlocked.Increment(ref modelCalls);
                if (call == 2)
                {
                    secondModelMessages = messages.ToList();
                }

                AIContent content = call == 1
                    ? new FunctionCallContent("call-1", FunctionName, new Dictionary<string, object?> { ["location"] = "Seattle" })
                    : new TextContent("Decision processed");
                return new ChatResponse([new ChatMessage(ChatRole.Assistant, [content])])
                    .ToChatResponseUpdates()
                    .ToAsyncEnumerable();
            });
        AIAgent innerAgent = new ChatClientAgent(
            chatClient.Object,
            name: useWorkflow ? "inner-agent" : AgentName,
            tools: [function]);
        AIAgent agent = useWorkflow
            ? new WorkflowBuilder(innerAgent.BindAsExecutor(new AIAgentHostOptions { EmitAgentUpdateEvents = true }))
                .Build()
                .AsAIAgent(name: AgentName)
            : innerAgent;

        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        builder.WebHost.UseTestServer();
        builder.AddAIAgent(AgentName, (_, _) => agent)
            .WithInMemorySessionStore(withIsolation: false);
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
            app.MapOpenAIResponses(agent);
        }
        await app.StartAsync();
        using HttpClient client = app.GetTestClient();
        var responsesUri = new Uri(resolveAgent ? "/v1/responses" : $"/{AgentName}/v1/responses", UriKind.Relative);
        string? conversationId = null;
        if (useConversation)
        {
            using StringContent createConversationContent = new("{}", Encoding.UTF8, "application/json");
            using HttpResponseMessage conversationResponse = await client.PostAsync(
                new Uri("/v1/conversations", UriKind.Relative),
                createConversationContent);
            conversationResponse.EnsureSuccessStatusCode();
            using JsonDocument conversationDocument = JsonDocument.Parse(await conversationResponse.Content.ReadAsStringAsync());
            conversationId = conversationDocument.RootElement.GetProperty("id").GetString();
        }

        string conversationProperty = conversationId is null
            ? string.Empty
            : $""","conversation":{JsonSerializer.Serialize(conversationId)}""";
        using StringContent initialContent = new(
            $$"""{"agent":{"name":"{{AgentName}}"},"input":"What is the weather in Seattle?","stream":true{{conversationProperty}}}""",
            Encoding.UTF8,
            "application/json");
        using HttpResponseMessage initialResponse = await client.PostAsync(responsesUri, initialContent);
        initialResponse.EnsureSuccessStatusCode();
        List<JsonElement> initialEvents = ParseSseEvents(await initialResponse.Content.ReadAsStringAsync());
        JsonElement approvalEvent = Assert.Single(initialEvents,
            item => item.GetProperty("type").GetString() == "response.function_approval.requested");
        string responseId = initialEvents.Last().GetProperty("response").GetProperty("id").GetString()!;
        string continuationProperty = conversationId is null
            ? $"\"previous_response_id\":{JsonSerializer.Serialize(responseId)}"
            : $"\"conversation\":{JsonSerializer.Serialize(conversationId)}";
        string approvalJson = $$"""
            {
              "agent": { "name": "{{AgentName}}" },
              {{continuationProperty}},
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
        using HttpResponseMessage response = await client.PostAsync(responsesUri, approvalContent);
        string responseBody = await response.Content.ReadAsStringAsync();

        // Assert
        Assert.True(response.IsSuccessStatusCode, responseBody);
        Assert.Equal(approved ? 1 : 0, functionInvocations);
        Assert.Equal(2, modelCalls);
        Assert.Equal(
            1,
            secondModelMessages!.Count(message =>
                message.Text?.Contains("What is the weather in Seattle?", StringComparison.Ordinal) == true));
        Assert.Contains("Decision processed", responseBody, StringComparison.Ordinal);
    }

    [Fact]
    public async Task FunctionApprovalResponse_Approved_GeneratesCorrectEvent_SuccessAsync()
    {
        // Arrange
        const string AgentName = "approval-response-approved-agent";
        const string RequestId = "req-789";
        const string FunctionName = "send_email";
        const string FunctionId = "call-ghi789";
        Dictionary<string, object?> arguments = new() { ["to"] = "user@example.com", ["subject"] = "Test" };

#pragma warning disable MEAI001 // Type is for evaluation purposes only and is subject to change or removal in future updates
        FunctionCallContent functionCall = new(FunctionId, FunctionName, arguments);
        ToolApprovalResponseContent approvalResponse = new(RequestId, approved: true, functionCall);
#pragma warning restore MEAI001

        HttpClient client = await this.CreateTestServerAsync(AgentName, "You are a test agent.", string.Empty, (msg) =>
            [approvalResponse]);

        // Act
        HttpResponseMessage httpResponse = await this.SendResponsesRequestAsync(client, AgentName, StreamingRequestJson);
        string sseContent = await httpResponse.Content.ReadAsStringAsync();
        List<JsonElement> events = ParseSseEvents(sseContent);

        // Assert
        Assert.NotEmpty(events);

        // Verify function approval responded event
        JsonElement approvalEvent = events.FirstOrDefault(e =>
            e.GetProperty("type").GetString() == "response.function_approval.responded");
        Assert.True(approvalEvent.ValueKind != JsonValueKind.Undefined, "approval response event not found");

        Assert.Equal(RequestId, approvalEvent.GetProperty("request_id").GetString());
        Assert.True(approvalEvent.GetProperty("approved").GetBoolean());
    }

    [Fact]
    public async Task FunctionApprovalResponse_Rejected_GeneratesCorrectEvent_SuccessAsync()
    {
        // Arrange
        const string AgentName = "approval-response-rejected-agent";
        const string RequestId = "req-999";
        const string FunctionName = "delete_file";
        const string FunctionId = "call-xyz999";

#pragma warning disable MEAI001 // Type is for evaluation purposes only and is subject to change or removal in future updates
        FunctionCallContent functionCall = new(FunctionId, FunctionName, new Dictionary<string, object?> { ["path"] = "/important.txt" });
        ToolApprovalResponseContent approvalResponse = new(RequestId, approved: false, functionCall);
#pragma warning restore MEAI001

        HttpClient client = await this.CreateTestServerAsync(AgentName, "You are a test agent.", string.Empty, (msg) =>
            [approvalResponse]);

        // Act
        HttpResponseMessage httpResponse = await this.SendResponsesRequestAsync(client, AgentName, StreamingRequestJson);
        string sseContent = await httpResponse.Content.ReadAsStringAsync();
        List<JsonElement> events = ParseSseEvents(sseContent);

        // Assert
        JsonElement approvalEvent = events.FirstOrDefault(e =>
            e.GetProperty("type").GetString() == "response.function_approval.responded");
        Assert.NotEqual(JsonValueKind.Undefined, approvalEvent.ValueKind);

        Assert.Equal(RequestId, approvalEvent.GetProperty("request_id").GetString());
        Assert.False(approvalEvent.GetProperty("approved").GetBoolean());
    }

    [Fact]
    public async Task FunctionApprovalResponse_EmitsCorrectEventSequence_SuccessAsync()
    {
        // Arrange
        const string AgentName = "approval-response-sequence-agent";

#pragma warning disable MEAI001 // Type is for evaluation purposes only and is subject to change or removal in future updates
        FunctionCallContent functionCall = new("call-1", "test_function", new Dictionary<string, object?>());
        ToolApprovalResponseContent approvalResponse = new("req-1", approved: true, functionCall);
#pragma warning restore MEAI001

        HttpClient client = await this.CreateTestServerAsync(AgentName, "You are a test agent.", string.Empty, (msg) =>
            [approvalResponse]);

        // Act
        HttpResponseMessage httpResponse = await this.SendResponsesRequestAsync(client, AgentName, StreamingRequestJson);
        string sseContent = await httpResponse.Content.ReadAsStringAsync();
        List<JsonElement> events = ParseSseEvents(sseContent);

        // Assert
        List<string?> eventTypes = events.ConvertAll(e => e.GetProperty("type").GetString());

        Assert.Contains("response.function_approval.responded", eventTypes);
        Assert.Contains("response.completed", eventTypes);
    }

    #endregion

    #region Mixed Content Tests

    [Fact]
    public async Task MixedContent_ApprovalRequestAndText_GeneratesMultipleEvents_SuccessAsync()
    {
        // Arrange
        const string AgentName = "mixed-approval-text-agent";

#pragma warning disable MEAI001 // Type is for evaluation purposes only and is subject to change or removal in future updates
        FunctionCallContent functionCall = new("call-mixed-1", "test", new Dictionary<string, object?>());
        ToolApprovalRequestContent approvalRequest = new("req-mixed-1", functionCall);
#pragma warning restore MEAI001

        HttpClient client = await this.CreateTestServerAsync(AgentName, "You are a test agent.", string.Empty, (msg) =>
        [
            new TextContent("I need approval for this function:"),
            approvalRequest
        ]);

        // Act
        HttpResponseMessage httpResponse = await this.SendResponsesRequestAsync(client, AgentName, StreamingRequestJson);
        string sseContent = await httpResponse.Content.ReadAsStringAsync();
        List<JsonElement> events = ParseSseEvents(sseContent);

        // Assert
        List<string?> eventTypes = events.ConvertAll(e => e.GetProperty("type").GetString());

        Assert.Contains("response.output_item.added", eventTypes);
        Assert.Contains("response.function_approval.requested", eventTypes);
    }

    [Fact]
    public async Task MixedContent_MultipleApprovalRequests_GeneratesMultipleEvents_SuccessAsync()
    {
        // Arrange
        const string AgentName = "multiple-approval-agent";

#pragma warning disable MEAI001 // Type is for evaluation purposes only and is subject to change or removal in future updates
        FunctionCallContent functionCall1 = new("call-multi-1", "function1", new Dictionary<string, object?>());
        ToolApprovalRequestContent approvalRequest1 = new("req-multi-1", functionCall1);

        FunctionCallContent functionCall2 = new("call-multi-2", "function2", new Dictionary<string, object?>());
        ToolApprovalRequestContent approvalRequest2 = new("req-multi-2", functionCall2);
#pragma warning restore MEAI001

        HttpClient client = await this.CreateTestServerAsync(AgentName, "You are a test agent.", string.Empty, (msg) =>
        [
            approvalRequest1,
            approvalRequest2
        ]);

        // Act
        HttpResponseMessage httpResponse = await this.SendResponsesRequestAsync(client, AgentName, StreamingRequestJson);
        string sseContent = await httpResponse.Content.ReadAsStringAsync();
        List<JsonElement> events = ParseSseEvents(sseContent);

        // Assert
        List<JsonElement> approvalEvents = events.Where(e =>
            e.GetProperty("type").GetString() == "response.function_approval.requested").ToList();

        Assert.Equal(2, approvalEvents.Count);
        Assert.Equal("req-multi-1", approvalEvents[0].GetProperty("request_id").GetString());
        Assert.Equal("req-multi-2", approvalEvents[1].GetProperty("request_id").GetString());
    }

    #endregion

    #region Helper Methods

    private static List<JsonElement> ParseSseEvents(string sseContent)
    {
        List<JsonElement> events = [];
        string[] lines = sseContent.Split('\n');

        for (int i = 0; i < lines.Length; i++)
        {
            string line = lines[i].TrimEnd('\r');

            if (line.StartsWith("event: ", StringComparison.Ordinal) && i + 1 < lines.Length)
            {
                string dataLine = lines[i + 1].TrimEnd('\r');
                if (dataLine.StartsWith("data: ", StringComparison.Ordinal))
                {
                    string jsonData = dataLine.Substring("data: ".Length);
                    JsonDocument doc = JsonDocument.Parse(jsonData);
                    events.Add(doc.RootElement.Clone());
                }
            }
        }

        return events;
    }

    #endregion
}
