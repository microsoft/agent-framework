// Copyright (c) Microsoft. All rights reserved.

#if NET10_0

using System;
using System.Collections.Generic;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using SampleApp;

namespace Microsoft.Agents.AI.Foundry.Hosting.UnitTests;

/// <summary>
/// Covers the browsing tool that the hosted research sample links from the Harness research sample.
/// </summary>
public sealed class WebBrowsingToolTests
{
    [Fact]
    public async Task DownloadUriAsync_UsesThePolicyValidatedAddressAsync()
    {
        // Arrange
        await using var server = new OneShotHttpServer("<html><body>pinned</body></html>");
        int resolutionCount = 0;
        var tool = new WebBrowsingTool(
            new WebBrowsingToolOptions { AllowedHosts = ["rebind.invalid"] },
            (host, _) =>
            {
                Assert.Equal("rebind.invalid", host);
                resolutionCount++;
                return Task.FromResult(new[] { IPAddress.Loopback });
            });

        // Act
        string result = await tool.DownloadUriAsync(
            $"http://rebind.invalid:{server.Port}/",
            TestContext.Current.CancellationToken);

        // Assert: the connection reuses the checked address instead of resolving the host again.
        Assert.Equal("pinned", result);
        Assert.Equal(1, resolutionCount);
    }

    [Fact]
    public async Task DownloadUriAsync_PreservesTheOriginalHostHeaderAsync()
    {
        // Arrange
        await using var server = new OneShotHttpServer("<html><body>host</body></html>");
        var tool = CreateTool(
            ["original-host.invalid"],
            (_, _) => Task.FromResult(new[] { IPAddress.Loopback }));

        // Act
        await tool.DownloadUriAsync(
            $"http://original-host.invalid:{server.Port}/resource",
            TestContext.Current.CancellationToken);

        // Assert
        string requestHeaders = await server.RequestHeaders;
        Assert.Contains(
            $"Host: original-host.invalid:{server.Port}",
            requestHeaders,
            StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task DownloadUriAsync_TriesEveryPolicyValidatedAddressAsync()
    {
        // Arrange: the first approved address refuses the connection.
        await using var server = new OneShotHttpServer("<html><body>second</body></html>");
        var tool = CreateTool(
            ["multiple.invalid"],
            (_, _) => Task.FromResult(new[] { IPAddress.Parse("127.0.0.2"), IPAddress.Loopback }));

        // Act
        string result = await tool.DownloadUriAsync(
            $"http://multiple.invalid:{server.Port}/",
            TestContext.Current.CancellationToken);

        // Assert
        Assert.Equal("second", result);
    }

    [Fact]
    public async Task DownloadUriAsync_RevalidatesRedirectDestinationsAsync()
    {
        // Arrange: an allowed host redirects to a host that resolves to a private address.
        await using var server = new OneShotHttpServer(
            "<html><body>redirect</body></html>",
            $"http://blocked.invalid:{GetUnusedPort()}/private");
        var resolvedHosts = new List<string>();
        var tool = new WebBrowsingTool(
            new WebBrowsingToolOptions
            {
                AllowedHosts = ["allowed.invalid"],
                AllowPublicNetworks = true,
            },
            (host, _) =>
            {
                resolvedHosts.Add(host);
                return Task.FromResult(new[] { IPAddress.Loopback });
            });

        // Act
        string result = await tool.DownloadUriAsync(
            $"http://allowed.invalid:{server.Port}/",
            TestContext.Current.CancellationToken);

        // Assert
        Assert.Contains(
            "resolves to a private/internal network address",
            result,
            StringComparison.OrdinalIgnoreCase);
        Assert.Equal(["allowed.invalid", "blocked.invalid"], resolvedHosts);
    }

    [Fact]
    public async Task DownloadUriAsync_BlocksTheUnspecifiedAddressAsNonPublicAsync()
    {
        // Arrange
        await using var server = new OneShotHttpServer("<html><body>local</body></html>");
        var tool = new WebBrowsingTool(
            new WebBrowsingToolOptions { AllowPublicNetworks = true },
            (_, _) => throw new InvalidOperationException("IP literals must not use DNS."));

        // Act
        string result = await tool.DownloadUriAsync(
            $"http://0.0.0.0:{server.Port}/",
            TestContext.Current.CancellationToken);

        // Assert
        Assert.Contains(
            "resolves to a private/internal network address",
            result,
            StringComparison.OrdinalIgnoreCase);
    }

    private static WebBrowsingTool CreateTool(
        IReadOnlyList<string> allowedHosts,
        Func<string, CancellationToken, Task<IPAddress[]>> resolver) =>
        new(new WebBrowsingToolOptions { AllowedHosts = allowedHosts }, resolver);

    private static int GetUnusedPort()
    {
        var listener = new TcpListener(IPAddress.Loopback, 0);
        listener.Start();
        int port = ((IPEndPoint)listener.LocalEndpoint).Port;
        listener.Stop();
        return port;
    }

    /// <summary>
    /// Serves one HTTP response on the loopback interface and records the request headers.
    /// </summary>
    private sealed class OneShotHttpServer : IAsyncDisposable
    {
        private readonly TcpListener _listener;
        private readonly CancellationTokenSource _cancellationTokenSource = new();
        private readonly Task _serverTask;
        private readonly TaskCompletionSource<string> _requestHeaders =
            new(TaskCreationOptions.RunContinuationsAsynchronously);

        public OneShotHttpServer(string responseBody, string? redirectLocation = null)
        {
            this._listener = new TcpListener(IPAddress.Loopback, 0);
            this._listener.Start();
            this.Port = ((IPEndPoint)this._listener.LocalEndpoint).Port;
            this._serverTask = this.ServeAsync(responseBody, redirectLocation);
        }

        public int Port { get; }

        public Task<string> RequestHeaders => this._requestHeaders.Task;

        public async ValueTask DisposeAsync()
        {
            await this._cancellationTokenSource.CancelAsync();
            this._listener.Dispose();

            try
            {
                await this._serverTask;
            }
            catch (OperationCanceledException)
            {
            }
            catch (SocketException) when (this._cancellationTokenSource.IsCancellationRequested)
            {
            }

            this._cancellationTokenSource.Dispose();
        }

        private async Task ServeAsync(string responseBody, string? redirectLocation)
        {
            using TcpClient client = await this._listener.AcceptTcpClientAsync(this._cancellationTokenSource.Token);
            await using NetworkStream stream = client.GetStream();

            var request = new StringBuilder();
            byte[] buffer = new byte[1024];
            while (!request.ToString().Contains("\r\n\r\n", StringComparison.Ordinal))
            {
                int bytesRead = await stream.ReadAsync(buffer, this._cancellationTokenSource.Token);
                if (bytesRead == 0)
                {
                    break;
                }

                request.Append(Encoding.ASCII.GetString(buffer, 0, bytesRead));
            }

            this._requestHeaders.TrySetResult(request.ToString());

            string response = redirectLocation is null
                ? $"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: {Encoding.UTF8.GetByteCount(responseBody)}\r\nConnection: close\r\n\r\n{responseBody}"
                : $"HTTP/1.1 302 Found\r\nLocation: {redirectLocation}\r\nContent-Length: 0\r\nConnection: close\r\n\r\n";
            await stream.WriteAsync(Encoding.UTF8.GetBytes(response), this._cancellationTokenSource.Token);
        }
    }
}
#endif
