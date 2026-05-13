// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Hosting.UnitTests;

/// <summary>
/// Unit tests for <see cref="SessionIsolationKeyProvider"/> and its contract.
/// </summary>
public class SessionIsolationKeyProviderTests
{
    /// <summary>
    /// Verify that a concrete provider can return a non-null isolation key.
    /// </summary>
    [Fact]
    public async Task GetSessionIsolationKeyAsyncReturnsNonNullKeyAsync()
    {
        // Arrange
        const string ExpectedKey = "test-key";
        var provider = new TestSessionIsolationKeyProvider(ExpectedKey);

        // Act
        string? result = await provider.GetSessionIsolationKeyAsync();

        // Assert
        Assert.Equal(ExpectedKey, result);
    }

    /// <summary>
    /// Verify that a concrete provider can return null when no key is available.
    /// </summary>
    [Fact]
    public async Task GetSessionIsolationKeyAsyncReturnsNullWhenNoKeyAvailableAsync()
    {
        // Arrange
        var provider = new TestSessionIsolationKeyProvider(null);

        // Act
        string? result = await provider.GetSessionIsolationKeyAsync();

        // Assert
        Assert.Null(result);
    }

    /// <summary>
    /// Verify that cancellation token is passed through to the provider implementation.
    /// </summary>
    [Fact]
    public async Task GetSessionIsolationKeyAsyncPassesCancellationTokenAsync()
    {
        // Arrange
        var provider = new TestCancellableSessionIsolationKeyProvider();
        using var cts = new CancellationTokenSource();
        cts.Cancel();

        // Act & Assert
        await Assert.ThrowsAsync<TaskCanceledException>(
            async () => await provider.GetSessionIsolationKeyAsync(cts.Token));
    }

    #region Test Implementations

    /// <summary>
    /// Test implementation of <see cref="SessionIsolationKeyProvider"/> for testing purposes.
    /// </summary>
    private sealed class TestSessionIsolationKeyProvider : SessionIsolationKeyProvider
    {
        private readonly string? _key;

        public TestSessionIsolationKeyProvider(string? key)
        {
            this._key = key;
        }

        public override ValueTask<string?> GetSessionIsolationKeyAsync(CancellationToken cancellationToken = default)
        {
            return new ValueTask<string?>(this._key);
        }
    }

    /// <summary>
    /// Test implementation that respects cancellation tokens.
    /// </summary>
    private sealed class TestCancellableSessionIsolationKeyProvider : SessionIsolationKeyProvider
    {
        public override async ValueTask<string?> GetSessionIsolationKeyAsync(CancellationToken cancellationToken = default)
        {
            await Task.Delay(1000, cancellationToken);
            return "key";
        }
    }

    #endregion
}
