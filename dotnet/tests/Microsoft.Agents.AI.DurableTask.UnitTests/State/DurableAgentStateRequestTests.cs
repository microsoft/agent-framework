// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using Microsoft.Agents.AI.DurableTask.State;

namespace Microsoft.Agents.AI.DurableTask.Tests.Unit.State;

public sealed class DurableAgentStateRequestTests
{
    [Fact]
    public void RequestSerializationDeserialization()
    {
        // Arrange
        RunRequest originalRequest = new("Hello, world!")
        {
            OrchestrationId = "orch-456"
        };
        DurableAgentStateRequest originalDurableRequest = DurableAgentStateRequest.FromRunRequest(originalRequest);

        // Act
        string jsonContent = JsonSerializer.Serialize(
            originalDurableRequest,
            DurableAgentStateJsonContext.Default.GetTypeInfo(typeof(DurableAgentStateRequest))!);

        DurableAgentStateRequest? convertedJsonContent = (DurableAgentStateRequest?)JsonSerializer.Deserialize(
            jsonContent,
            DurableAgentStateJsonContext.Default.GetTypeInfo(typeof(DurableAgentStateRequest))!);

        // Assert
        Assert.NotNull(convertedJsonContent);
        Assert.Equal(originalRequest.CorrelationId, convertedJsonContent.CorrelationId);
        Assert.Equal(originalRequest.OrchestrationId, convertedJsonContent.OrchestrationId);
    }
}
