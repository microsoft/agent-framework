// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.OpenAI.UnitTests;

/// <summary>
/// Unit tests for the <see cref="OpenAIResponses"/> helper facade.
/// </summary>
public class OpenAIResponsesTests
{
    [Fact]
    public void ToAgentRunRequest_StringInput_ProducesUserMessage()
    {
        // Arrange
        using var doc = JsonDocument.Parse("""{ "input": "Hello there" }""");

        // Act
        var request = OpenAIResponses.ToAgentRunRequest(doc.RootElement);

        // Assert
        var message = Assert.Single(request.Messages);
        Assert.Equal(ChatRole.User, message.Role);
        Assert.Equal("Hello there", message.Text);
        Assert.Null(request.Options);
    }

    [Fact]
    public void ToAgentRunRequest_DangerousClientFunctionOptInWithoutAgent_ThrowsNotSupportedException()
    {
        // Arrange
        using var doc = JsonDocument.Parse("""{ "input": "Hello there" }""");
#pragma warning disable MAAI001
        var mapOptions = new OpenAIResponsesMapOptions
        {
            DangerouslyAllowClientFunctionTools =
                new(OpenAIClientFunctionToolNameConflictBehavior.Reject())
        };
#pragma warning restore MAAI001

        // Act & Assert
        Assert.Throws<NotSupportedException>(() =>
            OpenAIResponses.ToAgentRunRequest(doc.RootElement, mapOptions));
    }

    [Fact]
    public void ToAgentRunRequest_DangerousClientFunctionOptInWithAgent_ReturnsRunOptions()
    {
        // Arrange
        using var doc = JsonDocument.Parse(
            """
            {
              "input": "Hello there",
              "tools": [
                {
                  "type": "function",
                  "name": "client_function",
                  "parameters": { "type": "object" }
                }
              ]
            }
            """);
        using var chatClient = new TestHelpers.SimpleMockChatClient();
        AIAgent agent = chatClient.AsAIAgent(name: "test-agent");
#pragma warning disable MAAI001
        var mapOptions = new OpenAIResponsesMapOptions
        {
            DangerouslyAllowClientFunctionTools =
                new(OpenAIClientFunctionToolNameConflictBehavior.Reject())
        };
#pragma warning restore MAAI001

        // Act
        OpenAIResponsesRunRequest request =
            OpenAIResponses.ToAgentRunRequest(doc.RootElement, agent, mapOptions);

        // Assert
        ChatClientAgentRunOptions runOptions =
            Assert.IsType<ChatClientAgentRunOptions>(request.Options);
        AIFunctionDeclaration function =
            Assert.IsAssignableFrom<AIFunctionDeclaration>(Assert.Single(runOptions.ChatOptions!.Tools!));
        Assert.Equal("client_function", function.Name);
    }

    [Fact]
    public void GetSessionStoreId_PreviousResponseId_IsReturned()
    {
        // Arrange
        using var doc = JsonDocument.Parse("""{ "input": "hi", "previous_response_id": "resp_abc" }""");
        var request = OpenAIResponses.ToAgentRunRequest(doc.RootElement);

        // Act & Assert
        Assert.Equal("resp_abc", OpenAIResponses.GetSessionStoreId(request));
    }

    [Fact]
    public void GetSessionStoreId_ConversationId_IsReturned()
    {
        // Arrange
        using var doc = JsonDocument.Parse("""{ "input": "hi", "conversation": "conv_xyz" }""");
        var request = OpenAIResponses.ToAgentRunRequest(doc.RootElement);

        // Act & Assert
        Assert.Equal("conv_xyz", OpenAIResponses.GetSessionStoreId(request));
    }

    [Fact]
    public void GetSessionStoreId_BothPresent_PrefersPreviousResponseId()
    {
        // Arrange
        using var doc = JsonDocument.Parse("""{ "input": "hi", "previous_response_id": "resp_abc", "conversation": "conv_xyz" }""");
        var request = OpenAIResponses.ToAgentRunRequest(doc.RootElement);

        // Act & Assert
        Assert.Equal("resp_abc", OpenAIResponses.GetSessionStoreId(request));
    }

    [Fact]
    public void GetSessionStoreId_NoContinuationKey_ReturnsNull()
    {
        // Arrange
        using var doc = JsonDocument.Parse("""{ "input": "hi" }""");
        var request = OpenAIResponses.ToAgentRunRequest(doc.RootElement);

        // Act & Assert
        Assert.Null(OpenAIResponses.GetSessionStoreId(request));
    }

    [Fact]
    public void ToAgentRunRequest_InvalidBody_ThrowsArgumentException()
    {
        // Arrange (missing the required "input" field)
        using var doc = JsonDocument.Parse("""{ "model": "x" }""");

        // Act & Assert
        Assert.Throws<ArgumentException>("body", () => OpenAIResponses.ToAgentRunRequest(doc.RootElement));
    }

    [Fact]
    public void ToAgentRunRequest_MalformedBody_ThrowsArgumentException()
    {
        // Arrange (an array is not a valid Responses body)
        using var doc = JsonDocument.Parse("""[ 1, 2, 3 ]""");

        // Act & Assert
        Assert.Throws<ArgumentException>("body", () => OpenAIResponses.ToAgentRunRequest(doc.RootElement));
    }

    [Fact]
    public void CreateResponseId_HasResponsePrefix()
    {
        // Act
        string id = OpenAIResponses.CreateResponseId();

        // Assert
        Assert.StartsWith("resp_", id);
    }

    [Fact]
    public void WriteResponse_RendersIdAndOutputText()
    {
        // Arrange
        var response = new AgentResponse(new ChatMessage(ChatRole.Assistant, "Hello from the agent"));
        const string ResponseId = "resp_test123";

        // Act
        JsonElement payload = OpenAIResponses.WriteResponse(response, ResponseId, conversationId: "conv_1");

        // Assert
        Assert.Equal(ResponseId, payload.GetProperty("id").GetString());
        Assert.Equal("conv_1", payload.GetProperty("conversation").GetProperty("id").GetString());
        Assert.Contains("Hello from the agent", payload.GetRawText());
    }
}
