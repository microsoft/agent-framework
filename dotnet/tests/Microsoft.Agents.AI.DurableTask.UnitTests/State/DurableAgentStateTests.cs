// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using Microsoft.Agents.AI.DurableTask.State;

namespace Microsoft.Agents.AI.DurableTask.Tests.Unit.State;

public sealed class DurableAgentStateTests
{
    [Fact]
    public void InvalidVersion()
    {
        // Arrange
        const string JsonText = """
            {
                "schemaVersion": "hello"
            }
            """;

        // Act & Assert
        Assert.Throws<InvalidOperationException>(
            () => JsonSerializer.Deserialize(JsonText, DurableAgentStateJsonContext.Default.DurableAgentState));
    }

    [Fact]
    public void BreakingVersion()
    {
        // Arrange
        const string JsonText = """
            {
                "schemaVersion": "2.0.0"
            }
            """;

        // Act & Assert
        Assert.Throws<InvalidOperationException>(
            () => JsonSerializer.Deserialize(JsonText, DurableAgentStateJsonContext.Default.DurableAgentState));
    }

    [Fact]
    public void MissingData()
    {
        // Arrange
        const string JsonText = """
            {
                "schemaVersion": "1.0.0"
            }
            """;

        // Act & Assert
        Assert.Throws<InvalidOperationException>(
            () => JsonSerializer.Deserialize(JsonText, DurableAgentStateJsonContext.Default.DurableAgentState));
    }

    [Fact]
    public void ExtraData()
    {
        // Arrange
        const string JsonText = """
            {
                "schemaVersion": "1.0.0",
                "data": {
                    "conversationHistory": [],
                    "extraField": "someValue"
                }
            }
            """;

        // Act
        DurableAgentState? state = JsonSerializer.Deserialize(JsonText, DurableAgentStateJsonContext.Default.DurableAgentState);

        // Assert
        Assert.NotNull(state?.Data?.ExtensionData);

        Assert.True(state.Data.ExtensionData!.ContainsKey("extraField"));
        Assert.Equal("someValue", state.Data.ExtensionData["extraField"]!.ToString());

        // Act
        string jsonState = JsonSerializer.Serialize(state, DurableAgentStateJsonContext.Default.DurableAgentState);
        JsonDocument? jsonDocument = JsonSerializer.Deserialize<JsonDocument>(jsonState);

        // Assert
        Assert.NotNull(jsonDocument);
        Assert.True(jsonDocument.RootElement.TryGetProperty("data", out JsonElement dataElement));
        Assert.True(dataElement.TryGetProperty("extraField", out JsonElement extraFieldElement));
        Assert.Equal("someValue", extraFieldElement.ToString());
    }

    [Fact]
    public void BasicState()
    {
        // Arrange
        const string JsonText = """
          {
              "schemaVersion": "1.0.0",
              "data": {
                  "conversationHistory": [
                      {
                          "$type": "request",
                          "correlationId": "12345",
                          "createdAt": "2024-01-01T12:00:00Z",
                          "messages": [
                              {
                                  "role": "user",
                                  "contents": [
                                      {
                                          "$type": "text",
                                          "text": "Hello, agent!"
                                      }
                                  ]
                              }
                          ]
                      },
                      {
                          "$type": "response",
                          "correlationId": "12345",
                          "createdAt": "2024-01-01T12:01:00Z",
                          "messages": [
                              {
                                  "role": "agent",
                                  "contents": [
                                      {
                                          "$type": "text",
                                          "text": "Hi user!"
                                      }
                                  ]
                              }
                          ]
                      }
                  ]
              }
          }
          """;

        // Act
        DurableAgentState? state = JsonSerializer.Deserialize(
            JsonText,
            DurableAgentStateJsonContext.Default.DurableAgentState);

        // Assert
        Assert.NotNull(state);
        Assert.Equal("1.0.0", state.SchemaVersion);
        Assert.NotNull(state.Data);

        Assert.Collection(state.Data.ConversationHistory,
            entry =>
            {
                Assert.IsType<DurableAgentStateRequest>(entry);
                Assert.Equal("12345", entry.CorrelationId);
                Assert.Equal(DateTimeOffset.Parse("2024-01-01T12:00:00Z"), entry.CreatedAt);
                Assert.Single(entry.Messages);
                Assert.Equal("user", entry.Messages[0].Role);
                DurableAgentStateContent content = Assert.Single(entry.Messages[0].Contents);
                DurableAgentStateTextContent textContent = Assert.IsType<DurableAgentStateTextContent>(content);
                Assert.Equal("Hello, agent!", textContent.Text);
            },
            entry =>
            {
                Assert.IsType<DurableAgentStateResponse>(entry);
                Assert.Equal("12345", entry.CorrelationId);
                Assert.Equal(DateTimeOffset.Parse("2024-01-01T12:01:00Z"), entry.CreatedAt);
                Assert.Single(entry.Messages);
                Assert.Equal("agent", entry.Messages[0].Role);
                Assert.Single(entry.Messages[0].Contents);
                DurableAgentStateContent content = Assert.Single(entry.Messages[0].Contents);
                DurableAgentStateTextContent textContent = Assert.IsType<DurableAgentStateTextContent>(content);
                Assert.Equal("Hi user!", textContent.Text);
            });
    }
}
