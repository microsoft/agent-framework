// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel.Primitives;
using System.Collections.Generic;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.OpenAI.UnitTests.ChatClient;

/// <summary>
/// Unit tests for the <see cref="StreamingUpdatePipelineResponse"/> class.
/// </summary>
public sealed class StreamingUpdatePipelineResponseTests
{
    /// <summary>
    /// Verify that Status property returns 200.
    /// </summary>
    [Fact]
    public void Status_ReturnsOkStatus()
    {
        // Arrange
        IAsyncEnumerable<AgentResponseUpdate> updates = CreateTestUpdatesAsync();
        PipelineResponse response = new StreamingUpdatePipelineResponse(updates);

        // Act
        int status = response.Status;

        // Assert
        Assert.Equal(200, status);
    }

    /// <summary>
    /// Verify that ReasonPhrase property returns "OK".
    /// </summary>
    [Fact]
    public void ReasonPhrase_ReturnsOk()
    {
        // Arrange
        IAsyncEnumerable<AgentResponseUpdate> updates = CreateTestUpdatesAsync();
        PipelineResponse response = new StreamingUpdatePipelineResponse(updates);

        // Act
        string reasonPhrase = response.ReasonPhrase;

        // Assert
        Assert.Equal("OK", reasonPhrase);
    }

    /// <summary>
    /// Verify that ContentStream getter returns null.
    /// </summary>
    [Fact]
    public void ContentStream_Get_ReturnsNull()
    {
        // Arrange
        IAsyncEnumerable<AgentResponseUpdate> updates = CreateTestUpdatesAsync();
        PipelineResponse response = new StreamingUpdatePipelineResponse(updates);

        // Act
        System.IO.Stream? contentStream = response.ContentStream;

        // Assert
        Assert.Null(contentStream);
    }

    /// <summary>
    /// Verify that ContentStream setter is a no-op.
    /// </summary>
    [Fact]
    public void ContentStream_Set_IsNoOp()
    {
        // Arrange
        IAsyncEnumerable<AgentResponseUpdate> updates = CreateTestUpdatesAsync();
        PipelineResponse response = new StreamingUpdatePipelineResponse(updates);
        var testStream = new System.IO.MemoryStream();

        // Act
        response.ContentStream = testStream;

        // Assert
        Assert.Null(response.ContentStream);

        testStream.Dispose();
    }

    /// <summary>
    /// Verify that Content property returns empty BinaryData.
    /// </summary>
    [Fact]
    public void Content_ReturnsEmptyBinaryData()
    {
        // Arrange
        IAsyncEnumerable<AgentResponseUpdate> updates = CreateTestUpdatesAsync();
        PipelineResponse response = new StreamingUpdatePipelineResponse(updates);

        // Act
        BinaryData content = response.Content;

        // Assert
        Assert.NotNull(content);
        Assert.Equal(string.Empty, content.ToString());
    }

    /// <summary>
    /// Verify that BufferContent throws NotSupportedException.
    /// </summary>
    [Fact]
    public void BufferContent_ThrowsNotSupportedException()
    {
        // Arrange
        IAsyncEnumerable<AgentResponseUpdate> updates = CreateTestUpdatesAsync();
        PipelineResponse response = new StreamingUpdatePipelineResponse(updates);

        // Act & Assert
        var exception = Assert.Throws<NotSupportedException>(() => response.BufferContent());
        Assert.Contains("Buffering content is not supported", exception.Message);
    }

    /// <summary>
    /// Verify that BufferContentAsync throws NotSupportedException.
    /// </summary>
    [Fact]
    public async Task BufferContentAsync_ThrowsNotSupportedExceptionAsync()
    {
        // Arrange
        IAsyncEnumerable<AgentResponseUpdate> updates = CreateTestUpdatesAsync();
        PipelineResponse response = new StreamingUpdatePipelineResponse(updates);

        // Act & Assert
        var exception = await Assert.ThrowsAsync<NotSupportedException>(
            async () => await response.BufferContentAsync());
        Assert.Contains("Buffering content asynchronously is not supported", exception.Message);
    }

    /// <summary>
    /// Verify that Dispose does not throw.
    /// </summary>
    [Fact]
    public void Dispose_DoesNotThrow()
    {
        // Arrange
        IAsyncEnumerable<AgentResponseUpdate> updates = CreateTestUpdatesAsync();
        PipelineResponse response = new StreamingUpdatePipelineResponse(updates);

        // Act & Assert
        response.Dispose();
    }

    private static async IAsyncEnumerable<AgentResponseUpdate> CreateTestUpdatesAsync()
    {
        yield return new AgentResponseUpdate(Microsoft.Extensions.AI.ChatRole.Assistant, "test");
        await Task.CompletedTask;
    }
}
