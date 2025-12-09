// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Net.Http;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.OpenAI.Tests;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.OpenAI.UnitTests;

/// <summary>
/// Tests for function approval request and response content types.
/// These are DevUI-specific extensions that allow approval workflows for function calls.
/// </summary>
public sealed class FunctionApprovalTests : ConformanceTestBase
{
    // Streaming request JSON for OpenAI Responses API
    private const string StreamingRequestJson = @"{""model"":""gpt-4o-mini"",""input"":""test"",""stream"":true}";

    #region FunctionApprovalRequestContent Tests

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
        FunctionApprovalRequestContent approvalRequest = new(RequestId, functionCall);
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
        FunctionApprovalRequestContent approvalRequest = new(RequestId, functionCall);
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
    public async Task FunctionApprovalRequest_EmitsCorrectEventSequence_SuccessAsync()
    {
        // Arrange
        const string AgentName = "approval-sequence-agent";

#pragma warning disable MEAI001 // Type is for evaluation purposes only and is subject to change or removal in future updates
        FunctionCallContent functionCall = new("call-1", "test_function", new Dictionary<string, object?>());
        FunctionApprovalRequestContent approvalRequest = new("req-1", functionCall);
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
        FunctionApprovalRequestContent approvalRequest = new("req-1", functionCall);
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

    #region FunctionApprovalResponseContent Tests

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
        FunctionApprovalResponseContent approvalResponse = new(RequestId, approved: true, functionCall);
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
        FunctionApprovalResponseContent approvalResponse = new(RequestId, approved: false, functionCall);
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
        FunctionApprovalResponseContent approvalResponse = new("req-1", approved: true, functionCall);
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
        FunctionApprovalRequestContent approvalRequest = new("req-mixed-1", functionCall);
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
        FunctionApprovalRequestContent approvalRequest1 = new("req-multi-1", functionCall1);

        FunctionCallContent functionCall2 = new("call-multi-2", "function2", new Dictionary<string, object?>());
        FunctionApprovalRequestContent approvalRequest2 = new("req-multi-2", functionCall2);
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
