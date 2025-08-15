// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using Microsoft.Extensions.AI.Agents.Runtime;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Moq;

namespace Microsoft.Extensions.AI.Agents.Hosting.UnitTests;

/// <summary>
/// Unit tests for <see cref="AgentActor"/>.
/// </summary>
public class AgentActorTests
{
    /// <summary>
    /// Verifies that calling DisposeAsync completes successfully without throwing an exception.
    /// </summary>
    [Fact]
    public async Task DisposeAsync_NoException_CompletesSuccessfullyAsync()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        var mockContext = new Mock<IActorRuntimeContext>();
        var mockLogger = NullLoggerFactory.Instance.CreateLogger<AgentActor>();
        var actor = new AgentActor(mockAgent.Object, mockContext.Object, mockLogger);

        // Act
        var valueTask = actor.DisposeAsync();

        // Assert
        Assert.True(valueTask.IsCompleted, "DisposeAsync should return a completed ValueTask.");
        await valueTask;
    }
}
