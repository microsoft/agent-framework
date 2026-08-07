// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Hosting.UnitTests;

/// <summary>
/// Unit tests for <see cref="AgentIsolationKeyProvider"/> and its contract.
/// </summary>
public class AgentIsolationKeyProviderTests
{
    /// <summary>
    /// Verify that a concrete provider can return a non-null isolation key.
    /// </summary>
    [Fact]
    public async Task GetIsolationKeyAsyncReturnsNonNullKeyAsync()
    {
        // Arrange
        const string ExpectedKey = "test-key";
        var provider = new TestAgentIsolationKeyProvider(ExpectedKey);

        // Act
        string? result = await provider.GetIsolationKeyAsync();

        // Assert
        Assert.Equal(ExpectedKey, result);
    }

    /// <summary>
    /// Verify that a concrete provider can return null when no key is available.
    /// </summary>
    [Fact]
    public async Task GetIsolationKeyAsyncReturnsNullWhenNoKeyAvailableAsync()
    {
        // Arrange
        var provider = new TestAgentIsolationKeyProvider(null);

        // Act
        string? result = await provider.GetIsolationKeyAsync();

        // Assert
        Assert.Null(result);
    }

    /// <summary>
    /// Verify that cancellation token is passed through to the provider implementation.
    /// </summary>
    [Fact]
    public async Task GetIsolationKeyAsyncPassesCancellationTokenAsync()
    {
        // Arrange
        var provider = new TestCancellableAgentIsolationKeyProvider();
        using var cts = new CancellationTokenSource();
        cts.Cancel();

        // Act & Assert
        await Assert.ThrowsAsync<TaskCanceledException>(
            async () => await provider.GetIsolationKeyAsync(cts.Token));
    }

    #region Test Implementations

    /// <summary>
    /// Test implementation of <see cref="AgentIsolationKeyProvider"/> for testing purposes.
    /// </summary>
    private sealed class TestAgentIsolationKeyProvider : AgentIsolationKeyProvider
    {
        private readonly string? _key;

        public TestAgentIsolationKeyProvider(string? key)
        {
            this._key = key;
        }

        public override ValueTask<string?> GetIsolationKeyAsync(CancellationToken cancellationToken = default)
        {
            return new ValueTask<string?>(this._key);
        }
    }

    /// <summary>
    /// Test implementation that respects cancellation tokens.
    /// </summary>
    private sealed class TestCancellableAgentIsolationKeyProvider : AgentIsolationKeyProvider
    {
        public override async ValueTask<string?> GetIsolationKeyAsync(CancellationToken cancellationToken = default)
        {
            await Task.Delay(1000, cancellationToken);
            return "key";
        }
    }

    #endregion
}
