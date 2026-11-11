// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;
using Azure.Core;
using Microsoft.Agents.AI.Foundry.UnitTests.Hosting;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Moq;

namespace Microsoft.Agents.AI.Foundry.Hosting.UnitTests;

[Collection(FoundryProjectEndpointEnvFixture.Name)]
public class FoundryToolboxServiceTests
{
    private const string TestEndpoint = "https://proj.example/api/projects/proj";

    [Fact]
    public void TokenScope_DefaultsToAzurePublicCloud()
    {
        // Act
        var options = new FoundryToolboxServiceOptions();

        // Assert
        Assert.Equal("https://ai.azure.com/.default", options.TokenScope);
    }

    [Fact]
    public void Constructor_InvalidAllowedOAuthConsentOrigin_Throws()
    {
        // Arrange
        var options = new FoundryToolboxServiceOptions
        {
            AllowedOAuthConsentOrigins =
                new HashSet<Uri> { new("https://auth.example.com/path") },
        };

        // Act
        void CreateService() => _ = new FoundryToolboxService(
            options,
            Mock.Of<TokenCredential>());

        // Assert
        Assert.Throws<ArgumentException>(CreateService);
    }

    [Fact]
    public async Task StartAsync_WithoutEndpoint_DisablesToolboxSupportAsync()
    {
        // Arrange: neither env var is set (tests may run in any CI environment).
        var savedFoundry = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT");
        var savedAzure = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT");
        Environment.SetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT", null);
        Environment.SetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT", null);
        try
        {
            var options = new FoundryToolboxServiceOptions();
            options.ToolboxNames.Add("any");
            var openCount = 0;
            await using var service = new FoundryToolboxService(options, Mock.Of<TokenCredential>())
            {
                ToolboxOpener = (_, _) =>
                {
                    openCount++;
                    return Task.FromResult(CreateOpenResult(new HttpClient()));
                },
            };

            // Act
            await service.StartAsync(CancellationToken.None);
            await using var scope = service.CreateRequestScope();
            var resolution = await scope.ResolveAsync(CancellationToken.None);

            // Assert
            Assert.Equal(FoundryToolboxStartupStatus.NoEndpoint, service.StartupStatus);
            Assert.Empty(service.ToolboxNames);
            Assert.Empty(resolution.Tools);
            Assert.Empty(resolution.Consents);
            Assert.Equal(0, openCount);
        }
        finally
        {
            Environment.SetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT", savedFoundry);
            Environment.SetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT", savedAzure);
        }
    }

    [Theory]
    [InlineData("")]
    [InlineData("/")]
    public async Task ResolveAsync_OpensToolboxAtProjectEndpointFromEnvironmentAsync(string suffix)
    {
        // Arrange: the platform injects FOUNDRY_PROJECT_ENDPOINT, with or without a trailing slash.
        await using var server = await ToolboxLoopbackServer.StartAsync();
        var saved = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT");
        Environment.SetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT", server.Endpoint + suffix);
        try
        {
            var options = new FoundryToolboxServiceOptions();
            options.ToolboxNames.Add("my-toolbox");
            await using var service = new FoundryToolboxService(options, CreateCredential());
            await service.StartAsync(CancellationToken.None);

            // Act
            await using var scope = service.CreateRequestScope();
            var resolution = await scope.ResolveAsync(CancellationToken.None);

            // Assert
            Assert.Equal("get_weather", Assert.Single(resolution.Tools).Name);
            Assert.Equal("my-toolbox", Assert.Single(server.RequestsFor("initialize")).ToolboxName);
        }
        finally
        {
            Environment.SetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT", saved);
        }
    }

    [Fact]
    public async Task ResolveAsync_EndpointOverrideWinsOverEnvAsync()
    {
        // Arrange
        await using var server = await ToolboxLoopbackServer.StartAsync();
        var saved = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT");
        Environment.SetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT", "https://from-env.invalid/api/projects/proj");
        try
        {
            var options = new FoundryToolboxServiceOptions { EndpointOverride = server.Endpoint };
            options.ToolboxNames.Add("tb");
            await using var service = new FoundryToolboxService(options, CreateCredential());
            await service.StartAsync(CancellationToken.None);

            // Act
            await using var scope = service.CreateRequestScope();
            var resolution = await scope.ResolveAsync(CancellationToken.None);

            // Assert
            Assert.Single(resolution.Tools);
            Assert.Single(server.RequestsFor("initialize"));
        }
        finally
        {
            Environment.SetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT", saved);
        }
    }

    [Fact]
    public async Task StartAsync_WithEndpointAndNoToolboxes_ReportsHealthyAsync()
    {
        // Arrange: no pre-registered toolboxes is a legitimate setup; readiness passes.
        var options = new FoundryToolboxServiceOptions
        {
            EndpointOverride = "http://127.0.0.1:1/unused",
        };

        await using var service = new FoundryToolboxService(options, Mock.Of<TokenCredential>());

        // Act
        await service.StartAsync(CancellationToken.None);

        // Assert
        Assert.Equal(FoundryToolboxStartupStatus.Healthy, service.StartupStatus);
        Assert.Empty(service.ToolboxNames);
    }

    [Fact]
    public async Task StartAsync_DuplicateNames_OpensEachToolboxOncePerResponseAsync()
    {
        // Arrange
        var options = new FoundryToolboxServiceOptions { EndpointOverride = TestEndpoint };
        options.ToolboxNames.Add("tb");
        options.ToolboxNames.Add("TB");
        var opened = new ConcurrentBag<string>();
        await using var service = new FoundryToolboxService(options, Mock.Of<TokenCredential>())
        {
            ToolboxOpener = (name, _) =>
            {
                opened.Add(name);
                return Task.FromResult(CreateOpenResult(new HttpClient()));
            },
        };

        // Act
        await service.StartAsync(CancellationToken.None);
        await using var scope = service.CreateRequestScope();
        await scope.ResolveAsync(CancellationToken.None);

        // Assert
        Assert.Equal("tb", Assert.Single(service.ToolboxNames));
        Assert.Equal("tb", Assert.Single(opened));
    }

    [Theory]
    [InlineData("../../admin")]
    [InlineData("..%2f..%2fadmin")]
    [InlineData("%2e%2e/%2e%2e/admin")]
    [InlineData("%25252525252f")]
    [InlineData("a/b")]
    [InlineData("..")]
    [InlineData(".")]
    [InlineData("box\\..\\secret")]
    [InlineData("foo?x=1")]
    [InlineData("foo#frag")]
    [InlineData("bad%3fx=1")]
    [InlineData("tb%23frag")]
    [InlineData("a%2fb")]
    public async Task StartAsync_RejectsNonSingleSegmentToolboxNameAsync(string unsafeName)
    {
        // Arrange: a name that would move the request target — path separators, relative-path
        // segments, a query/fragment delimiter that ends the path early, or any of their
        // percent-encoded forms — must be rejected before any request URL is built, so it can never
        // carry the managed-identity token to an unintended endpoint.
        var options = new FoundryToolboxServiceOptions { EndpointOverride = TestEndpoint };
        options.ToolboxNames.Add(unsafeName);
        var openCount = 0;
        await using var service = new FoundryToolboxService(options, Mock.Of<TokenCredential>())
        {
            ToolboxOpener = (_, _) =>
            {
                openCount++;
                return Task.FromResult(CreateOpenResult(new HttpClient()));
            },
        };

        // Act
        var exception = await Record.ExceptionAsync(() => service.StartAsync(CancellationToken.None));

        // Assert: startup fails before the container serves traffic, and nothing is opened.
        Assert.IsType<InvalidOperationException>(exception);
        Assert.Contains(unsafeName, exception.Message, StringComparison.Ordinal);
        Assert.Equal(FoundryToolboxStartupStatus.Pending, service.StartupStatus);
        Assert.Equal(0, openCount);
    }

    [Theory]
    [InlineData("my-toolbox")]
    [InlineData("sales")]
    [InlineData("box.v2")]
    [InlineData("a..b")]
    [InlineData("tb:v1")]
    [InlineData("tb@1")]
    [InlineData("a(b)")]
    public async Task StartAsync_AllowsWellFormedSingleSegmentNameAsync(string validName)
    {
        // Arrange: a well-formed single-segment name — including names that merely contain a
        // character which stays inside the path segment (a dot that is not a standalone relative-path
        // segment, or reserved characters such as ':' , '@' , and parentheses) — must still resolve
        // through the opener. Validation is effect-based (does the name change the request target?),
        // so it does not lock out legitimate names.
        AITool tool = AIFunctionFactory.Create(() => "ok", name: "some_tool");
        var options = new FoundryToolboxServiceOptions { EndpointOverride = TestEndpoint };
        options.ToolboxNames.Add(validName);
        await using var service = new FoundryToolboxService(options, Mock.Of<TokenCredential>())
        {
            ToolboxOpener = (_, _) => Task.FromResult(CreateOpenResult(new HttpClient(), tool)),
        };

        // Act
        await service.StartAsync(CancellationToken.None);
        await using var scope = service.CreateRequestScope();
        var resolution = await scope.ResolveAsync(CancellationToken.None);

        // Assert
        Assert.Equal(validName, Assert.Single(service.ToolboxNames));
        Assert.Same(tool, Assert.Single(resolution.Tools));
    }

    [Fact]
    public async Task StartAsync_OpensNoToolboxAsync()
    {
        // Arrange
        var options = new FoundryToolboxServiceOptions { EndpointOverride = TestEndpoint };
        options.ToolboxNames.Add("tb");
        var openCount = 0;
        await using var service = new FoundryToolboxService(options, Mock.Of<TokenCredential>())
        {
            ToolboxOpener = (_, _) =>
            {
                openCount++;
                return Task.FromResult(CreateOpenResult(new HttpClient()));
            },
        };

        // Act
        await service.StartAsync(CancellationToken.None);

        // Assert: startup has no caller, so it opens nothing that a caller could later share.
        Assert.Equal(FoundryToolboxStartupStatus.Healthy, service.StartupStatus);
        Assert.Equal(0, openCount);
    }

    [Fact]
    public async Task ResolveAsync_UnreachableToolbox_ContinuesWithoutItsToolsAsync()
    {
        // Arrange
        var logs = new RecordingLoggerFactory();
        var options = new FoundryToolboxServiceOptions { EndpointOverride = "http://127.0.0.1:1/unreachable" };
        options.ToolboxNames.Add("broken-toolbox");
        await using var service = new FoundryToolboxService(
            options,
            CreateCredential(),
            logs.CreateLogger<FoundryToolboxService>());
        await service.StartAsync(CancellationToken.None);
        await using var scope = service.CreateRequestScope();

        // Act
        var resolution = await scope.ResolveAsync(CancellationToken.None);

        // Assert: the response continues without the toolbox, and the failure is logged.
        Assert.Empty(resolution.Tools);
        Assert.Empty(resolution.Consents);
        var warning = Assert.Single(logs.Entries, entry => entry.Level == LogLevel.Warning);
        Assert.Equal("LogToolboxUnavailableForResponse", warning.EventId.Name);
        Assert.NotNull(warning.Exception);
    }

    [Fact]
    public async Task ResolveAsync_ToolboxTimesOutWithoutResponseCancellation_ContinuesWithOtherToolboxesAsync()
    {
        // Arrange: an HTTP timeout surfaces as an OperationCanceledException that the response did not request.
        AITool tool = AIFunctionFactory.Create(() => "ok", name: "fast_tool");
        var options = new FoundryToolboxServiceOptions { EndpointOverride = TestEndpoint };
        options.ToolboxNames.Add("slow");
        options.ToolboxNames.Add("fast");
        await using var service = new FoundryToolboxService(options, Mock.Of<TokenCredential>())
        {
            ToolboxOpener = (name, _) => name == "slow"
                ? Task.FromException<FoundryToolboxService.ToolboxOpenResult>(new TaskCanceledException("Timed out."))
                : Task.FromResult(CreateOpenResult(new HttpClient(), tool)),
        };
        await service.StartAsync(CancellationToken.None);
        await using var scope = service.CreateRequestScope();

        // Act
        var resolution = await scope.ResolveAsync(CancellationToken.None);

        // Assert
        Assert.Same(tool, Assert.Single(resolution.Tools));
    }

    [Fact]
    public async Task ResolveAsync_ResponseCanceled_PropagatesAndScopeEndsOpenedConnectionsAsync()
    {
        // Arrange: one toolbox opens before the response is canceled while another is still opening.
        using var cancellation = new CancellationTokenSource();
        var handler = new TrackingHttpMessageHandler();
        var options = new FoundryToolboxServiceOptions { EndpointOverride = TestEndpoint };
        options.ToolboxNames.Add("opened");
        options.ToolboxNames.Add("canceled");
        await using var service = new FoundryToolboxService(options, Mock.Of<TokenCredential>())
        {
            ToolboxOpener = (name, cancellationToken) =>
            {
                if (name == "opened")
                {
                    return Task.FromResult(CreateOpenResult(new HttpClient(handler)));
                }

                cancellation.Cancel();
                return Task.FromCanceled<FoundryToolboxService.ToolboxOpenResult>(cancellationToken);
            },
        };
        await service.StartAsync(CancellationToken.None);
        var scope = service.CreateRequestScope();

        // Act
        await Assert.ThrowsAnyAsync<OperationCanceledException>(
            async () => await scope.ResolveAsync(cancellation.Token));
        await scope.DisposeAsync();

        // Assert: the connection that opened before cancellation is still ended with the response.
        Assert.True(handler.IsDisposed);
    }

    [Fact]
    public async Task ResolveAsync_ConsentRequired_ReturnsConsentsWithoutToolsAsync()
    {
        // Arrange
        var handler = new TrackingHttpMessageHandler();
        McpConsentInfo consent = new("needs-consent", "send", "https://auth.example.com/consent");
        var options = new FoundryToolboxServiceOptions { EndpointOverride = TestEndpoint };
        options.ToolboxNames.Add("ready");
        options.ToolboxNames.Add("needs-consent");
        await using var service = new FoundryToolboxService(options, Mock.Of<TokenCredential>())
        {
            ToolboxOpener = (name, _) => Task.FromResult(name == "ready"
                ? CreateOpenResult(new HttpClient(handler), AIFunctionFactory.Create(() => "ok", name: "ready_tool"))
                : new FoundryToolboxService.ToolboxOpenResult(Connection: null, Consents: [consent])),
        };
        await service.StartAsync(CancellationToken.None);
        var scope = service.CreateRequestScope();

        // Act
        var resolution = await scope.ResolveAsync(CancellationToken.None);
        await scope.DisposeAsync();

        // Assert: the turn stops on consent, and the connection that did open is still ended.
        Assert.Empty(resolution.Tools);
        Assert.Same(consent, Assert.Single(resolution.Consents));
        Assert.True(handler.IsDisposed);
    }

    [Fact]
    public async Task ResolveAsync_ConcurrentScopes_OpenIndependentConnectionsAsync()
    {
        // Arrange
        var options = new FoundryToolboxServiceOptions { EndpointOverride = TestEndpoint };
        options.ToolboxNames.Add("shared-toolbox");
        var handlers = new ConcurrentBag<TrackingHttpMessageHandler>();
        var bothOpenersEntered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var concurrentOpenCount = 0;
        var openCount = 0;
        await using var service = new FoundryToolboxService(options, Mock.Of<TokenCredential>())
        {
            ToolboxOpener = async (_, cancellationToken) =>
            {
                if (Interlocked.Increment(ref concurrentOpenCount) == 2)
                {
                    bothOpenersEntered.TrySetResult();
                }

                await bothOpenersEntered.Task.WaitAsync(TimeSpan.FromSeconds(5), cancellationToken);
                var handler = new TrackingHttpMessageHandler();
                handlers.Add(handler);
                var openNumber = Interlocked.Increment(ref openCount);
                return CreateOpenResult(
                    new HttpClient(handler),
                    AIFunctionFactory.Create(() => "ok", name: $"scoped_tool_{openNumber}"));
            },
        };
        await service.StartAsync(CancellationToken.None);

        async Task<AITool> ResolveInOwnScopeAsync()
        {
            await using var scope = service.CreateRequestScope();
            return Assert.Single((await scope.ResolveAsync(CancellationToken.None)).Tools);
        }

        // Act
        var tools = await Task.WhenAll(
            Task.Run(ResolveInOwnScopeAsync),
            Task.Run(ResolveInOwnScopeAsync));

        // Assert
        Assert.Equal(2, openCount);
        Assert.NotSame(tools[0], tools[1]);
        Assert.Equal(2, handlers.Count);
        Assert.All(handlers, static item => Assert.True(item.IsDisposed));
    }

    [Fact]
    public async Task DisposeAsync_EndsEveryConnectionTheScopeOpenedAsync()
    {
        // Arrange
        var options = new FoundryToolboxServiceOptions { EndpointOverride = TestEndpoint };
        options.ToolboxNames.Add("shared-toolbox");
        var handler = new TrackingHttpMessageHandler();
        var client = new TrackingAsyncDisposable();
        await using var service = new FoundryToolboxService(options, Mock.Of<TokenCredential>())
        {
            ToolboxOpener = (_, _) => Task.FromResult(CreateOpenResult(new HttpClient(handler), client)),
        };
        await service.StartAsync(CancellationToken.None);
        var scope = service.CreateRequestScope();
        await scope.ResolveAsync(CancellationToken.None);

        // Act
        await scope.DisposeAsync();

        // Assert
        Assert.True(client.IsDisposed);
        Assert.True(handler.IsDisposed);
    }

    [Theory]
    [InlineData("MCP client")]
    [InlineData("HTTP client")]
    public async Task DisposeAsync_DisposalFailure_DisposesRemainingResourcesAndDoesNotThrowAsync(string failingResource)
    {
        // Arrange: one toolbox's resource fails to dispose; every other resource must still be released.
        var logs = new RecordingLoggerFactory();
        var handlers = new ConcurrentDictionary<string, TrackingHttpMessageHandler>(StringComparer.Ordinal);
        var clients = new ConcurrentDictionary<string, TrackingAsyncDisposable>(StringComparer.Ordinal);
        var options = new FoundryToolboxServiceOptions { EndpointOverride = TestEndpoint };
        options.ToolboxNames.Add("throws");
        options.ToolboxNames.Add("continues");
        await using var service = new FoundryToolboxService(
            options,
            Mock.Of<TokenCredential>(),
            logs.CreateLogger<FoundryToolboxService>())
        {
            ToolboxOpener = (name, _) =>
            {
                var fails = name == "throws";
                var handler = handlers[name] = new TrackingHttpMessageHandler(
                    throwOnDispose: fails && failingResource == "HTTP client");
                var client = clients[name] = new TrackingAsyncDisposable(
                    throwOnDispose: fails && failingResource == "MCP client");
                return Task.FromResult(CreateOpenResult(new HttpClient(handler), client));
            },
        };
        await service.StartAsync(CancellationToken.None);
        logs.Entries.Clear();
        var scope = service.CreateRequestScope();
        await scope.ResolveAsync(CancellationToken.None);

        // Act
        var exception = await Record.ExceptionAsync(async () => await scope.DisposeAsync());

        // Assert: a failed MCP client disposal still releases its HTTP client.
        Assert.Null(exception);
        Assert.All(clients.Values, static client => Assert.True(client.IsDisposed));
        Assert.All(handlers.Values, static handler => Assert.True(handler.IsDisposed));
        var warning = Assert.Single(logs.Entries, entry => entry.Level == LogLevel.Warning);
        Assert.Equal(0, warning.EventId.Id);
        Assert.Equal("LogToolboxResourceDisposalFailed", warning.EventId.Name);
        Assert.Equal(
            $"Failed to dispose {failingResource} for toolbox throws owned by response scope.",
            warning.Message);
        Assert.IsType<InvalidOperationException>(warning.Exception);
        AssertProperty(warning.Properties, "Resource", failingResource);
        AssertProperty(warning.Properties, "ToolboxName", "throws");
        AssertProperty(warning.Properties, "Owner", "response scope");
        AssertProperty(
            warning.Properties,
            "{OriginalFormat}",
            "Failed to dispose {Resource} for toolbox {ToolboxName} owned by {Owner}.");
    }

    [Fact]
    public async Task ResolveAsync_InactiveScope_ReturnsNoToolsAsync()
    {
        // Arrange
        await using var scope = FoundryToolboxService.ToolboxRequestScope.CreateInactive();

        // Act
        var resolution = await scope.ResolveAsync(CancellationToken.None);

        // Assert
        Assert.Empty(resolution.Tools);
        Assert.Empty(resolution.Consents);
    }

    private static TokenCredential CreateCredential()
    {
        var credential = new Mock<TokenCredential>();
        credential
            .Setup(c => c.GetTokenAsync(It.IsAny<TokenRequestContext>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new AccessToken("test-token", DateTimeOffset.UtcNow.AddHours(1)));
        return credential.Object;
    }

    private static FoundryToolboxService.ToolboxOpenResult CreateOpenResult(HttpClient httpClient, params AITool[] tools) =>
        new(new FoundryToolboxService.ToolboxConnection(Client: null, httpClient, tools), Consents: null);

    private static FoundryToolboxService.ToolboxOpenResult CreateOpenResult(HttpClient httpClient, IAsyncDisposable client) =>
        new(new FoundryToolboxService.ToolboxConnection(client, httpClient, []), Consents: null);

    private static void AssertProperty(
        IReadOnlyList<KeyValuePair<string, object?>> properties,
        string name,
        object expectedValue)
    {
        var property = Assert.Single(properties, property => property.Key == name);
        Assert.Equal(expectedValue, property.Value);
    }

    private sealed class TrackingAsyncDisposable(bool throwOnDispose = false) : IAsyncDisposable
    {
        internal bool IsDisposed { get; private set; }

        public ValueTask DisposeAsync()
        {
            this.IsDisposed = true;
            return throwOnDispose
                ? ValueTask.FromException(new InvalidOperationException("Simulated MCP client disposal failure."))
                : default;
        }
    }

    private sealed class TrackingHttpMessageHandler : HttpMessageHandler
    {
        private readonly bool _throwOnDispose;

        internal TrackingHttpMessageHandler(bool throwOnDispose = false)
        {
            this._throwOnDispose = throwOnDispose;
        }

        internal bool IsDisposed { get; private set; }

        protected override Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken) =>
            throw new NotSupportedException();

        protected override void Dispose(bool disposing)
        {
            this.IsDisposed = true;
            base.Dispose(disposing);
            if (this._throwOnDispose)
            {
                throw new InvalidOperationException("Simulated HTTP client disposal failure.");
            }
        }
    }
}
