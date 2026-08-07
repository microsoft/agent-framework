// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Hosting.UnitTests;

/// <summary>
/// Unit tests for <see cref="StoreIsolationKeyProvider"/> and its contract.
/// </summary>
public class StoreIsolationKeyProviderTests
{
    /// <summary>
    /// Verify that a concrete provider can return a non-null isolation key.
    /// </summary>
    [Fact]
    public async Task GetStoreIsolationKeyAsyncReturnsNonNullKeyAsync()
    {
        // Arrange
        const string ExpectedKey = "test-key";
        var provider = new TestStoreIsolationKeyProvider(ExpectedKey);

        // Act
        string? result = await provider.GetStoreIsolationKeyAsync();

        // Assert
        Assert.Equal(ExpectedKey, result);
    }

    /// <summary>
    /// Verify that a concrete provider can return null when no key is available.
    /// </summary>
    [Fact]
    public async Task GetStoreIsolationKeyAsyncReturnsNullWhenNoKeyAvailableAsync()
    {
        // Arrange
        var provider = new TestStoreIsolationKeyProvider(null);

        // Act
        string? result = await provider.GetStoreIsolationKeyAsync();

        // Assert
        Assert.Null(result);
    }

    /// <summary>
    /// Verify that cancellation token is passed through to the provider implementation.
    /// </summary>
    [Fact]
    public async Task GetStoreIsolationKeyAsyncPassesCancellationTokenAsync()
    {
        // Arrange
        var provider = new TestCancellableStoreIsolationKeyProvider();
        using var cts = new CancellationTokenSource();
        cts.Cancel();

        // Act & Assert
        await Assert.ThrowsAsync<TaskCanceledException>(
            async () => await provider.GetStoreIsolationKeyAsync(cts.Token));
    }

    #region Test Implementations

    /// <summary>
    /// Test implementation of <see cref="StoreIsolationKeyProvider"/> for testing purposes.
    /// </summary>
    private sealed class TestStoreIsolationKeyProvider : StoreIsolationKeyProvider
    {
        private readonly string? _key;

        public TestStoreIsolationKeyProvider(string? key)
        {
            this._key = key;
        }

        public override ValueTask<string?> GetStoreIsolationKeyAsync(CancellationToken cancellationToken = default)
        {
            return new ValueTask<string?>(this._key);
        }
    }

    /// <summary>
    /// Test implementation that respects cancellation tokens.
    /// </summary>
    private sealed class TestCancellableStoreIsolationKeyProvider : StoreIsolationKeyProvider
    {
        public override async ValueTask<string?> GetStoreIsolationKeyAsync(CancellationToken cancellationToken = default)
        {
            await Task.Delay(1000, cancellationToken);
            return "key";
        }
    }

    #endregion
}
