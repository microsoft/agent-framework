// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using GitHub.Copilot;

namespace Microsoft.Agents.AI.GitHub.Copilot.UnitTests;

[Collection(nameof(FeatureUsageTestGroup))]
public sealed class FeatureUsageActivationTests : IDisposable
{
    public FeatureUsageActivationTests() => FeatureUsageAssert.Reset();

    [Fact]
    public async Task RunAsync_WhenCancelled_ActivatesGitHubCopilotAsync()
    {
        // Arrange
        CopilotClient copilotClient = new(new CopilotClientOptions());
        var agent = new GitHubCopilotAgent(copilotClient, ownsClient: false, tools: null);
        using var cancellationSource = new CancellationTokenSource();
        cancellationSource.Cancel();

        // Act
        _ = await Assert.ThrowsAnyAsync<OperationCanceledException>(
            () => agent.RunAsync("hello", cancellationToken: cancellationSource.Token));

        // Assert
        FeatureUsageAssert.Marked(57);
    }

    [Fact]
    public async Task RunStreamingAsync_IsColdAndActivatesGitHubCopilotAsync()
    {
        // Arrange
        CopilotClient copilotClient = new(new CopilotClientOptions());
        var agent = new GitHubCopilotAgent(copilotClient, ownsClient: false, tools: null);
        using var cancellationSource = new CancellationTokenSource();
        cancellationSource.Cancel();

        // Act
        IAsyncEnumerable<AgentResponseUpdate> stream =
            agent.RunStreamingAsync("hello", cancellationToken: cancellationSource.Token);

        // Assert
        Assert.Equal(string.Empty, FeatureUsage.ApplyToUserAgent(string.Empty));
        await using IAsyncEnumerator<AgentResponseUpdate> enumerator = stream.GetAsyncEnumerator();
        _ = await Assert.ThrowsAnyAsync<OperationCanceledException>(
            async () => await enumerator.MoveNextAsync());
        FeatureUsageAssert.Marked(57);
    }

    public void Dispose() => FeatureUsageAssert.Reset();
}
