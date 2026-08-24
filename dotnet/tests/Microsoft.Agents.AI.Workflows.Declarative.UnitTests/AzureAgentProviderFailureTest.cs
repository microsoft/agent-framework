// Copyright (c) Microsoft. All rights reserved.

using System.Linq;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using OpenAI.Responses;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests;

/// <summary>
/// Verifies that <see cref="AzureAgentProvider"/> restores the failure signal that
/// <c>Microsoft.Extensions.AI.OpenAI</c> drops when it maps the Responses <c>response.failed</c>
/// event onto a contentless update.
/// </summary>
public sealed class AzureAgentProviderFailureTest(ITestOutputHelper output) : WorkflowTest(output)
{
    private const string AgentName = "TestAgent";

    [Fact]
    public async Task FailedResponseYieldsErrorContentAsync()
    {
        // Arrange
        AgentResponseUpdate failed = FailedUpdate("server_error", "Something went wrong.");

        // Act
        AgentResponseUpdate[] results = await CollectAsync(failed);

        // Assert
        // The failed update is replaced, not supplemented: its raw representation carries provider
        // error text that must not reach clients.
        AgentResponseUpdate result = Assert.Single(results);
        ErrorContent error = Assert.Single(result.Contents.OfType<ErrorContent>());
        Assert.Equal("Something went wrong.", error.Message);
        Assert.Equal("server_error", error.ErrorCode);
        Assert.Null((result.RawRepresentation as ChatResponseUpdate)?.RawRepresentation as StreamingResponseFailedUpdate);

        // Correlation is carried onto the replacement.
        Assert.Equal(AgentName, result.AuthorName);
        Assert.Equal(failed.ResponseId, result.ResponseId);
    }

    [Fact]
    public async Task FailedResponseWithoutErrorDetailUsesFallbackAsync()
    {
        // Arrange - a failed response that carries no error object.
        AgentResponseUpdate failed = FailedUpdate(errorCode: null, errorMessage: null);

        // Act
        AgentResponseUpdate[] results = await CollectAsync(failed);

        // Assert - a failure with no detail must still explain itself.
        ErrorContent error = Assert.Single(results.SelectMany(update => update.Contents).OfType<ErrorContent>());
        Assert.False(string.IsNullOrWhiteSpace(error.Message));
        Assert.False(string.IsNullOrWhiteSpace(error.ErrorCode));
    }

    [Fact]
    public async Task SuccessfulUpdatesPassThroughUntouchedAsync()
    {
        // Arrange
        AgentResponseUpdate text = new(ChatRole.Assistant, [new TextContent("All good.")]);
        AgentResponseUpdate contentless = new(ChatRole.Assistant, []);

        // Act
        AgentResponseUpdate[] results = await CollectAsync(text, contentless);

        // Assert - no synthesized failure is introduced.
        Assert.Equal(2, results.Length);
        Assert.Empty(results.SelectMany(update => update.Contents).OfType<ErrorContent>());
        Assert.All(results, update => Assert.Equal(AgentName, update.AuthorName));
    }

    private static async Task<AgentResponseUpdate[]> CollectAsync(params AgentResponseUpdate[] updates) =>
        [.. await AgentUpdateTestHelpers.ApplyFailureDetectionAsync(AgentName, updates)];

    /// <summary>
    /// Builds the update shape produced for a <c>response.failed</c> event.
    /// </summary>
    private static AgentResponseUpdate FailedUpdate(string? errorCode, string? errorMessage) =>
        AgentUpdateTestHelpers.CreateFailedUpdate(errorCode, errorMessage);
}
