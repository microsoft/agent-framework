// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.Hosting.OpenAI.UnitTests;

/// <summary>
/// Tests for converting Responses API input messages to agent messages.
/// </summary>
public sealed class InputMessageTests
{
    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public void ToChatMessage_FunctionApprovalResponse_PreservesDecisionAndFunctionCall(bool approved)
    {
        // Arrange
        string json = $$"""
            {
              "type": "message",
              "role": "user",
              "content": [
                { "type": "input_text", "text": "My decision" },
                {
                  "request_id": "executor:request-1",
                  "approved": {{(approved ? "true" : "false")}},
                  "function_call": {
                    "id": "call-1",
                    "name": "get_weather",
                    "arguments": {
                      "location": "Seattle",
                      "count": 2,
                      "options": { "forecast": true },
                      "days": ["Monday", "Tuesday"],
                      "unit": null
                    }
                  },
                  "type": "function_approval_response"
                }
              ]
            }
            """;
        InputMessage input = JsonSerializer.Deserialize(json, OpenAIHostingJsonContext.Default.InputMessage)!;

        // Act
        ChatMessage message = input.ToChatMessage();

        // Assert
        Assert.Equal(ChatRole.User, message.Role);
        Assert.Equal(2, message.Contents.Count);
        Assert.Equal("My decision", Assert.IsType<TextContent>(message.Contents[0]).Text);
        ToolApprovalResponseContent approval = Assert.IsType<ToolApprovalResponseContent>(message.Contents[1]);
        Assert.Equal("executor:request-1", approval.RequestId);
        Assert.Equal(approved, approval.Approved);
        FunctionCallContent functionCall = Assert.IsType<FunctionCallContent>(approval.ToolCall);
        Assert.Equal("call-1", functionCall.CallId);
        Assert.Equal("get_weather", functionCall.Name);
        Assert.NotNull(functionCall.Arguments);
        Assert.Equal("Seattle", Assert.IsType<JsonElement>(functionCall.Arguments["location"]).GetString());
        Assert.Equal(2, Assert.IsType<JsonElement>(functionCall.Arguments["count"]).GetInt32());
        Assert.True(Assert.IsType<JsonElement>(functionCall.Arguments["options"]).GetProperty("forecast").GetBoolean());
        Assert.Equal("Tuesday", Assert.IsType<JsonElement>(functionCall.Arguments["days"])[1].GetString());
        Assert.Null(functionCall.Arguments["unit"]);
        Assert.Same(input.Content.Contents![1], approval.RawRepresentation);
    }

    [Theory]
    [InlineData("{}")]
    [InlineData("null")]
    public void ToChatMessage_FunctionApprovalResponse_HandlesNoArguments(string arguments)
    {
        // Arrange
        string json = $$"""
            {
              "role": "user",
              "content": [{
                "type": "function_approval_response",
                "request_id": "request-1",
                "approved": true,
                "function_call": { "id": "call-1", "name": "get_time", "arguments": {{arguments}} }
              }]
            }
            """;
        InputMessage input = JsonSerializer.Deserialize(json, OpenAIHostingJsonContext.Default.InputMessage)!;

        // Act
        ChatMessage message = input.ToChatMessage();

        // Assert
        ToolApprovalResponseContent approval = Assert.IsType<ToolApprovalResponseContent>(Assert.Single(message.Contents));
        FunctionCallContent functionCall = Assert.IsType<FunctionCallContent>(approval.ToolCall);
        Assert.True(functionCall.Arguments is null || functionCall.Arguments.Count == 0);
    }

    [Theory]
    [InlineData("Hello")]
    [InlineData("")]
    public void ToChatMessage_Text_PreservesRoleAndText(string text)
    {
        // Arrange
        InputMessage input = new() { Role = ChatRole.User, Content = text };

        // Act
        ChatMessage message = input.ToChatMessage();

        // Assert
        Assert.Equal(ChatRole.User, message.Role);
        Assert.Equal(text, message.Text);
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task ToChatMessage_FunctionApprovalResponse_ResumesWorkflowAsync(bool approved)
    {
        // Arrange
        List<string> toolInvocations = [];
        AIFunction tool = new ApprovalRequiredAIFunction(AIFunctionFactory.Create((string location) =>
        {
            toolInvocations.Add(location);
            return "Sunny";
        }, "get_weather"));
        int modelCalls = 0;
        Mock<IChatClient> chatClient = new();
        chatClient.Setup(c => c.GetStreamingResponseAsync(
            It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions?>(), It.IsAny<CancellationToken>()))
            .Returns(() =>
            {
                AIContent content = ++modelCalls == 1
                    ? new FunctionCallContent("call-1", "get_weather", new Dictionary<string, object?> { ["location"] = "Seattle" })
                    : new TextContent("Decision processed");
                return new ChatResponse([new ChatMessage(ChatRole.Assistant, [content])]).ToChatResponseUpdates().ToAsyncEnumerable();
            });
        AIAgent innerAgent = new ChatClientAgent(chatClient.Object, name: "weather-agent", tools: [tool]);
        Workflow workflow = new WorkflowBuilder(innerAgent.BindAsExecutor(
            new AIAgentHostOptions { InterceptUserInputRequests = false, EmitAgentUpdateEvents = true })).Build();
        AIAgent agent = workflow.AsAIAgent("workflow-agent");
        AgentSession session = await agent.CreateSessionAsync();
        List<AgentResponseUpdate> initialUpdates = await agent.RunStreamingAsync("What is the weather?", session).ToListAsync();
        ToolApprovalRequestContent request = Assert.Single(initialUpdates
            .Where(u => u.RawRepresentation is RequestInfoEvent)
            .SelectMany(u => u.Contents).OfType<ToolApprovalRequestContent>());
        Assert.Empty(toolInvocations);
        string json = $$"""
            {
              "role": "user",
              "content": [{
                "type": "function_approval_response",
                "request_id": {{JsonSerializer.Serialize(request.RequestId)}},
                "approved": {{(approved ? "true" : "false")}},
                "function_call": { "id": "call-1", "name": "get_weather", "arguments": { "location": "Seattle" } }
              }]
            }
            """;
        InputMessage input = JsonSerializer.Deserialize(json, OpenAIHostingJsonContext.Default.InputMessage)!;

        // Act
        List<AgentResponseUpdate> updates = await agent.RunStreamingAsync(input.ToChatMessage(), session).ToListAsync();

        // Assert
        Assert.Equal(2, modelCalls);
        Assert.Equal(approved ? ["Seattle"] : System.Array.Empty<string>(), toolInvocations);
        Assert.Contains(updates, update => update.Text == "Decision processed");
        Assert.DoesNotContain(updates.SelectMany(u => u.Contents), content => content is ToolApprovalRequestContent);
    }
}
