// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Channels;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Purview.Models.Common;
using Microsoft.Agents.AI.Purview.Models.Jobs;
using Microsoft.Agents.AI.Purview.Models.Requests;
using Microsoft.Agents.AI.Purview.Models.Responses;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging.Abstractions;
using Moq;

namespace Microsoft.Agents.AI.Purview.UnitTests;

/// <summary>
/// Unit tests for the <see cref="ScopedContentProcessor"/> class.
/// </summary>
public sealed class ScopedContentProcessorTests
{
    private readonly Mock<IPurviewClient> _mockPurviewClient;
    private readonly Mock<ICacheProvider> _mockCacheProvider;
    private readonly Mock<IChannelHandler> _mockChannelHandler;
    private readonly ScopedContentProcessor _processor;

    public ScopedContentProcessorTests()
    {
        this._mockPurviewClient = new Mock<IPurviewClient>();
        this._mockCacheProvider = new Mock<ICacheProvider>();
        this._mockChannelHandler = new Mock<IChannelHandler>();
        this._processor = new ScopedContentProcessor(
            this._mockPurviewClient.Object,
            this._mockCacheProvider.Object,
            this._mockChannelHandler.Object);
    }

    #region ProcessMessagesAsync Tests

    [Fact]
    public async Task ProcessMessagesAsync_WithBlockAccessAction_ReturnsShouldBlockTrueAsync()
    {
        // Arrange
        var messages = new List<ChatMessage>
        {
            new (ChatRole.User, "Test message")
        };
        var settings = CreateValidPurviewSettings();
        var tokenInfo = new TokenInfo { TenantId = "tenant-123", UserId = "user-123", ClientId = "client-123" };

        this._mockPurviewClient.Setup(x => x.GetUserInfoFromTokenAsync(It.IsAny<CancellationToken>(), null))
            .ReturnsAsync(tokenInfo);

        var psResponse = new ProtectionScopesResponse
        {
            Scopes =
            [
                new()
                {
                    Activities = ProtectionScopeActivities.UploadText,
                    Locations =
                    [
                        new ("microsoft.graph.policyLocationApplication", "app-123")
                    ],
                    ExecutionMode = ExecutionMode.EvaluateInline
                }
            ]
        };

        this._mockCacheProvider.Setup(x => x.GetAsync<ProtectionScopesCacheKey, ProtectionScopesResponse>(
            It.IsAny<ProtectionScopesCacheKey>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(psResponse);

        var pcResponse = new ProcessContentResponse
        {
            PolicyActions =
            [
                new() { Action = DlpAction.BlockAccess }
            ]
        };

        this._mockPurviewClient.Setup(x => x.ProcessContentAsync(
            It.IsAny<ProcessContentRequest>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(pcResponse);

        // Act
        var result = await this._processor.ProcessMessagesAsync(
            messages, "session-123", Activity.UploadText, settings, "user-123", CancellationToken.None);

        // Assert
        Assert.True(result.shouldBlock);
        Assert.Equal("user-123", result.userId);
    }

    [Fact]
    public async Task ProcessMessagesAsync_WithRestrictionActionBlock_ReturnsShouldBlockTrueAsync()
    {
        // Arrange
        var messages = new List<ChatMessage>
        {
            new (ChatRole.User, "Test message")
        };
        var settings = CreateValidPurviewSettings();
        var tokenInfo = new TokenInfo { TenantId = "tenant-123", UserId = "user-123", ClientId = "client-123" };

        this._mockPurviewClient.Setup(x => x.GetUserInfoFromTokenAsync(It.IsAny<CancellationToken>(), null))
            .ReturnsAsync(tokenInfo);

        var psResponse = new ProtectionScopesResponse
        {
            Scopes =
            [
                new()
                {
                    Activities = ProtectionScopeActivities.UploadText,
                    Locations =
                    [
                        new ("microsoft.graph.policyLocationApplication", "app-123")
                    ],
                    ExecutionMode = ExecutionMode.EvaluateInline
                }
            ]
        };

        this._mockCacheProvider.Setup(x => x.GetAsync<ProtectionScopesCacheKey, ProtectionScopesResponse>(
            It.IsAny<ProtectionScopesCacheKey>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(psResponse);

        var pcResponse = new ProcessContentResponse
        {
            PolicyActions =
            [
                new() { RestrictionAction = RestrictionAction.Block }
            ]
        };

        this._mockPurviewClient.Setup(x => x.ProcessContentAsync(
            It.IsAny<ProcessContentRequest>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(pcResponse);

        // Act
        var result = await this._processor.ProcessMessagesAsync(
            messages, "session-123", Activity.UploadText, settings, "user-123", CancellationToken.None);

        // Assert
        Assert.True(result.shouldBlock);
        Assert.Equal("user-123", result.userId);
    }

    [Fact]
    public async Task ProcessMessagesAsync_WithNoBlockingActions_ReturnsShouldBlockFalseAsync()
    {
        // Arrange
        var messages = new List<ChatMessage>
        {
            new (ChatRole.User, "Test message")
        };
        var settings = CreateValidPurviewSettings();
        var tokenInfo = new TokenInfo { TenantId = "tenant-123", UserId = "user-123", ClientId = "client-123" };

        this._mockPurviewClient.Setup(x => x.GetUserInfoFromTokenAsync(It.IsAny<CancellationToken>(), null))
            .ReturnsAsync(tokenInfo);

        var psResponse = new ProtectionScopesResponse
        {
            Scopes =
            [
                new()
                {
                    Activities = ProtectionScopeActivities.UploadText,
                    Locations =
                    [
                        new("microsoft.graph.policyLocationApplication", "app-123")
                    ],
                    ExecutionMode = ExecutionMode.EvaluateInline
                }
            ]
        };

        this._mockCacheProvider.Setup(x => x.GetAsync<ProtectionScopesCacheKey, ProtectionScopesResponse>(
            It.IsAny<ProtectionScopesCacheKey>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(psResponse);

        var pcResponse = new ProcessContentResponse
        {
            PolicyActions =
            [
                new() { Action = DlpAction.NotifyUser }
            ]
        };

        this._mockPurviewClient.Setup(x => x.ProcessContentAsync(
            It.IsAny<ProcessContentRequest>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(pcResponse);

        // Act
        var result = await this._processor.ProcessMessagesAsync(
            messages, "session-123", Activity.UploadText, settings, "user-123", CancellationToken.None);

        // Assert
        Assert.False(result.shouldBlock);
        Assert.Equal("user-123", result.userId);
    }

    [Fact]
    public async Task ProcessMessagesAsync_DeduplicatesCombinedPolicyActionsByActionAndRestrictionAsync()
    {
        // Arrange
        List<ChatMessage> messages =
        [
            new(ChatRole.User, "Test message")
        ];
        PurviewSettings settings = CreateValidPurviewSettings();
        TokenInfo tokenInfo = new() { TenantId = "tenant-123", UserId = "user-123", ClientId = "client-123" };
        DlpActionInfo processContentAction = new() { Action = DlpAction.BlockAccess, RestrictionAction = RestrictionAction.Block };
        DlpActionInfo duplicateScopeAction = new() { Action = DlpAction.BlockAccess, RestrictionAction = RestrictionAction.Block };
        DlpActionInfo restrictionOnlyAction = new() { RestrictionAction = RestrictionAction.Block };
        ProcessContentResponse pcResponse = new()
        {
            PolicyActions =
            [
                processContentAction
            ]
        };
        ProtectionScopesResponse psResponse = new()
        {
            Scopes =
            [
                new()
                {
                    Activities = ProtectionScopeActivities.UploadText,
                    Locations =
                    [
                        new("microsoft.graph.policyLocationApplication", "app-123")
                    ],
                    ExecutionMode = ExecutionMode.EvaluateInline,
                    PolicyActions =
                    [
                        duplicateScopeAction,
                        restrictionOnlyAction
                    ]
                }
            ]
        };

        this._mockPurviewClient.Setup(x => x.GetUserInfoFromTokenAsync(It.IsAny<CancellationToken>(), null))
            .ReturnsAsync(tokenInfo);

        this._mockCacheProvider.Setup(x => x.GetAsync<ProtectionScopesCacheKey, ProtectionScopesResponse>(
            It.IsAny<ProtectionScopesCacheKey>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(psResponse);

        this._mockPurviewClient.Setup(x => x.ProcessContentAsync(
            It.IsAny<ProcessContentRequest>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(pcResponse);

        // Act
        await this._processor.ProcessMessagesAsync(
            messages, "session-123", Activity.UploadText, settings, "user-123", CancellationToken.None);

        // Assert
        Assert.NotNull(pcResponse.PolicyActions);
        Assert.Equal(2, pcResponse.PolicyActions.Count);
        Assert.Same(processContentAction, pcResponse.PolicyActions[0]);
        Assert.Same(restrictionOnlyAction, pcResponse.PolicyActions[1]);
    }

    [Fact]
    public async Task ProcessMessagesAsync_UsesCachedProtectionScopes_WhenAvailableAsync()
    {
        // Arrange
        var messages = new List<ChatMessage>
        {
            new (ChatRole.User, "Test message")
        };
        var settings = CreateValidPurviewSettings();
        var tokenInfo = new TokenInfo { TenantId = "tenant-123", UserId = "user-123", ClientId = "client-123" };

        this._mockPurviewClient.Setup(x => x.GetUserInfoFromTokenAsync(It.IsAny<CancellationToken>(), null))
            .ReturnsAsync(tokenInfo);

        var cachedPsResponse = new ProtectionScopesResponse
        {
            Scopes =
            [
                new()
                {
                    Activities = ProtectionScopeActivities.UploadText,
                    Locations =
                    [
                        new ("microsoft.graph.policyLocationApplication", "app-123")
                    ],
                    ExecutionMode = ExecutionMode.EvaluateInline
                }
            ]
        };

        this._mockCacheProvider.Setup(x => x.GetAsync<ProtectionScopesCacheKey, ProtectionScopesResponse>(
            It.IsAny<ProtectionScopesCacheKey>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(cachedPsResponse);

        var pcResponse = new ProcessContentResponse
        {
            PolicyActions = []
        };

        this._mockPurviewClient.Setup(x => x.ProcessContentAsync(
            It.IsAny<ProcessContentRequest>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(pcResponse);

        // Act
        await this._processor.ProcessMessagesAsync(
            messages, "session-123", Activity.UploadText, settings, "user-123", CancellationToken.None);

        // Assert
        this._mockPurviewClient.Verify(x => x.GetProtectionScopesAsync(
            It.IsAny<ProtectionScopesRequest>(), It.IsAny<CancellationToken>()), Times.Never);
    }

    [Fact]
    public async Task ProcessMessagesAsync_InvalidatesCache_WhenProtectionScopeModifiedAsync()
    {
        // Arrange
        var messages = new List<ChatMessage>
        {
            new (ChatRole.User, "Test message")
        };
        var settings = CreateValidPurviewSettings();
        var tokenInfo = new TokenInfo { TenantId = "tenant-123", UserId = "user-123", ClientId = "client-123" };

        this._mockPurviewClient.Setup(x => x.GetUserInfoFromTokenAsync(It.IsAny<CancellationToken>(), null))
            .ReturnsAsync(tokenInfo);

        var psResponse = new ProtectionScopesResponse
        {
            ScopeIdentifier = "etag-1",
            Scopes =
            [
                new()
                {
                    Activities = ProtectionScopeActivities.UploadText,
                    Locations =
                    [
                        new ("microsoft.graph.policyLocationApplication", "app-123")
                    ],
                    ExecutionMode = ExecutionMode.EvaluateInline
                }
            ]
        };

        this._mockCacheProvider.Setup(x => x.GetAsync<ProtectionScopesCacheKey, ProtectionScopesResponse>(
            It.IsAny<ProtectionScopesCacheKey>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(psResponse);

        var pcResponse = new ProcessContentResponse
        {
            ProtectionScopeState = ProtectionScopeState.Modified,
            PolicyActions = []
        };

        this._mockPurviewClient.Setup(x => x.ProcessContentAsync(
            It.IsAny<ProcessContentRequest>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(pcResponse);

        // Act
        await this._processor.ProcessMessagesAsync(
            messages, "session-123", Activity.UploadText, settings, "user-123", CancellationToken.None);

        // Assert
        this._mockCacheProvider.Verify(x => x.RemoveAsync(
            It.IsAny<ProtectionScopesCacheKey>(), It.IsAny<CancellationToken>()), Times.Once);
    }

    [Fact]
    public async Task ProcessMessagesAsync_SendsContentActivities_WhenNoApplicableScopesAsync()
    {
        // Arrange
        var messages = new List<ChatMessage>
        {
            new (ChatRole.User, "Test message")
        };
        var settings = CreateValidPurviewSettings();
        var tokenInfo = new TokenInfo { TenantId = "tenant-123", UserId = "user-123", ClientId = "client-123" };

        this._mockPurviewClient.Setup(x => x.GetUserInfoFromTokenAsync(It.IsAny<CancellationToken>(), null))
            .ReturnsAsync(tokenInfo);

        var psResponse = new ProtectionScopesResponse
        {
            Scopes =
            [
                new()
                {
                    Activities = ProtectionScopeActivities.UploadText,
                    Locations =
                    [
                        new ("microsoft.graph.policyLocationApplication", "app-456")
                    ]
                }
            ]
        };

        this._mockCacheProvider.Setup(x => x.GetAsync<ProtectionScopesCacheKey, ProtectionScopesResponse>(
            It.IsAny<ProtectionScopesCacheKey>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(psResponse);

        // Act
        await this._processor.ProcessMessagesAsync(
            messages, "session-123", Activity.UploadText, settings, "user-123", CancellationToken.None);

        // Assert
        // Content activities are now queued as background jobs, not called directly
        this._mockChannelHandler.Verify(x => x.QueueJob(It.IsAny<ContentActivityJob>()), Times.Once);
        this._mockPurviewClient.Verify(x => x.ProcessContentAsync(
            It.IsAny<ProcessContentRequest>(), It.IsAny<CancellationToken>()), Times.Never);
    }

    [Fact]
    public async Task ProcessMessagesAsync_WithNoTenantId_ThrowsPurviewExceptionAsync()
    {
        // Arrange
        var messages = new List<ChatMessage>
        {
            new (ChatRole.User, "Test message")
        };
        var settings = new PurviewSettings("TestApp"); // No TenantId
        var tokenInfo = new TokenInfo { UserId = "user-123", ClientId = "client-123" }; // No TenantId

        this._mockPurviewClient.Setup(x => x.GetUserInfoFromTokenAsync(It.IsAny<CancellationToken>(), null))
            .ReturnsAsync(tokenInfo);

        // Act & Assert
        var exception = await Assert.ThrowsAsync<PurviewRequestException>(() =>
            this._processor.ProcessMessagesAsync(messages, "session-123", Activity.UploadText, settings, "user-123", CancellationToken.None));

        Assert.Contains("No tenant id provided or inferred", exception.Message);
    }

    [Fact]
    public async Task ProcessMessagesAsync_WithNoUserId_ThrowsPurviewExceptionAsync()
    {
        // Arrange
        var messages = new List<ChatMessage>
        {
            new (ChatRole.User, "Test message")
        };
        var settings = CreateValidPurviewSettings();
        var tokenInfo = new TokenInfo { TenantId = "tenant-123", ClientId = "client-123" }; // No UserId

        this._mockPurviewClient.Setup(x => x.GetUserInfoFromTokenAsync(It.IsAny<CancellationToken>(), null))
            .ReturnsAsync(tokenInfo);

        // Act & Assert
        var exception = await Assert.ThrowsAsync<PurviewRequestException>(() =>
            this._processor.ProcessMessagesAsync(messages, "session-123", Activity.UploadText, settings, null, CancellationToken.None));

        Assert.Contains("No user id provided or inferred", exception.Message);
    }

    [Fact]
    public async Task ProcessMessagesAsync_ExtractsUserIdFromMessageAdditionalProperties_Async()
    {
        // Arrange
        var messages = new List<ChatMessage>
        {
            new (ChatRole.User, "Test message")
            {
                AdditionalProperties = new AdditionalPropertiesDictionary
                {
                    { "userId", "user-from-props" }
                }
            }
        };
        var settings = CreateValidPurviewSettings();
        var tokenInfo = new TokenInfo { TenantId = "tenant-123", ClientId = "client-123" };

        this._mockPurviewClient.Setup(x => x.GetUserInfoFromTokenAsync(It.IsAny<CancellationToken>(), null))
            .ReturnsAsync(tokenInfo);

        var psResponse = new ProtectionScopesResponse { Scopes = [] };
        this._mockCacheProvider.Setup(x => x.GetAsync<ProtectionScopesCacheKey, ProtectionScopesResponse>(
            It.IsAny<ProtectionScopesCacheKey>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(psResponse);

        // Act
        var result = await this._processor.ProcessMessagesAsync(
            messages, "session-123", Activity.UploadText, settings, null, CancellationToken.None);

        // Assert
        Assert.Equal("user-from-props", result.userId);
    }

    [Fact]
    public async Task ProcessMessagesAsync_ExtractsUserIdFromMessageAuthorName_WhenValidGuidAsync()
    {
        // Arrange
        var userId = Guid.NewGuid().ToString();
        var messages = new List<ChatMessage>
        {
            new (ChatRole.User, "Test message")
            {
                AuthorName = userId
            }
        };
        var settings = CreateValidPurviewSettings();
        var tokenInfo = new TokenInfo { TenantId = "tenant-123", ClientId = "client-123" };

        this._mockPurviewClient.Setup(x => x.GetUserInfoFromTokenAsync(It.IsAny<CancellationToken>(), null))
            .ReturnsAsync(tokenInfo);

        var psResponse = new ProtectionScopesResponse { Scopes = [] };
        this._mockCacheProvider.Setup(x => x.GetAsync<ProtectionScopesCacheKey, ProtectionScopesResponse>(
            It.IsAny<ProtectionScopesCacheKey>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(psResponse);

        // Act
        var result = await this._processor.ProcessMessagesAsync(
            messages, "session-123", Activity.UploadText, settings, null, CancellationToken.None);

        // Assert
        Assert.Equal(userId, result.userId);
    }

    [Fact]
    public async Task ProcessMessagesAsync_CacheMiss_QueuesScopeRetrievalJobAndCallsProcessContentAsync()
    {
        // Arrange
        var messages = new List<ChatMessage>
        {
            new (ChatRole.User, "Test message")
        };
        var settings = CreateValidPurviewSettings();
        var tokenInfo = new TokenInfo { TenantId = "tenant-123", UserId = "user-123", ClientId = "client-123" };
        this._mockPurviewClient.Setup(x => x.GetUserInfoFromTokenAsync(It.IsAny<CancellationToken>(), null))
            .ReturnsAsync(tokenInfo);

        this._mockCacheProvider.Setup(x => x.GetAsync<ProtectionScopesCacheKey, ProtectionScopesResponse>(
            It.IsAny<ProtectionScopesCacheKey>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync((ProtectionScopesResponse?)null);

        this._mockPurviewClient.Setup(x => x.ProcessContentAsync(
            It.IsAny<ProcessContentRequest>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ProcessContentResponse());

        // Act
        await this._processor.ProcessMessagesAsync(
            messages, "session-123", Activity.UploadText, settings, "user-123", CancellationToken.None);

        // Assert: ProcessContent runs in the foreground; GetProtectionScopes is queued as a background job.
        this._mockPurviewClient.Verify(x => x.ProcessContentAsync(
            It.IsAny<ProcessContentRequest>(), It.IsAny<CancellationToken>()), Times.Once);
        this._mockPurviewClient.Verify(x => x.GetProtectionScopesAsync(
            It.IsAny<ProtectionScopesRequest>(), It.IsAny<CancellationToken>()), Times.Never);
        this._mockChannelHandler.Verify(x => x.QueueJob(It.IsAny<ScopeRetrievalJob>()), Times.Once);
    }

    [Fact]
    public async Task ProcessMessagesAsync_CacheMiss_WithProcessContentBlockAction_ReturnsShouldBlockTrueAsync()
    {
        // Arrange
        var messages = new List<ChatMessage>
        {
            new (ChatRole.User, "Test message")
        };
        var settings = CreateValidPurviewSettings();
        var tokenInfo = new TokenInfo { TenantId = "tenant-123", UserId = "user-123", ClientId = "client-123" };
        this._mockPurviewClient.Setup(x => x.GetUserInfoFromTokenAsync(It.IsAny<CancellationToken>(), null))
            .ReturnsAsync(tokenInfo);

        this._mockCacheProvider.Setup(x => x.GetAsync<ProtectionScopesCacheKey, ProtectionScopesResponse>(
            It.IsAny<ProtectionScopesCacheKey>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync((ProtectionScopesResponse?)null);

        var pcResponse = new ProcessContentResponse
        {
            PolicyActions =
            [
                new() { Action = DlpAction.BlockAccess }
            ]
        };

        this._mockPurviewClient.Setup(x => x.ProcessContentAsync(
            It.IsAny<ProcessContentRequest>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(pcResponse);

        // Act
        var result = await this._processor.ProcessMessagesAsync(
            messages, "session-123", Activity.UploadText, settings, "user-123", CancellationToken.None);

        // Assert
        Assert.True(result.shouldBlock);
        this._mockChannelHandler.Verify(x => x.QueueJob(It.IsAny<ScopeRetrievalJob>()), Times.Once);
    }

    [Fact]
    public async Task ProcessMessagesAsync_CacheMiss_StillCallsProcessContentWhenScopeJobCannotQueueAsync()
    {
        // Arrange
        var messages = new List<ChatMessage>
        {
            new (ChatRole.User, "Test message")
        };
        var settings = CreateValidPurviewSettings();
        var tokenInfo = new TokenInfo { TenantId = "tenant-123", UserId = "user-123", ClientId = "client-123" };
        this._mockPurviewClient.Setup(x => x.GetUserInfoFromTokenAsync(It.IsAny<CancellationToken>(), null))
            .ReturnsAsync(tokenInfo);

        this._mockCacheProvider.Setup(x => x.GetAsync<ProtectionScopesCacheKey, ProtectionScopesResponse>(
            It.IsAny<ProtectionScopesCacheKey>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync((ProtectionScopesResponse?)null);

        this._mockChannelHandler.Setup(x => x.QueueJob(It.IsAny<ScopeRetrievalJob>()))
            .Throws(new PurviewJobException("queue unavailable"));

        this._mockPurviewClient.Setup(x => x.ProcessContentAsync(
            It.IsAny<ProcessContentRequest>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ProcessContentResponse());

        // Act
        await this._processor.ProcessMessagesAsync(
            messages, "session-123", Activity.UploadText, settings, "user-123", CancellationToken.None);

        // Assert: scope warmup is attempted, and ProcessContent still runs when it can't be queued.
        this._mockChannelHandler.Verify(x => x.QueueJob(It.IsAny<ScopeRetrievalJob>()), Times.Once);
        this._mockPurviewClient.Verify(x => x.ProcessContentAsync(
            It.IsAny<ProcessContentRequest>(), It.IsAny<CancellationToken>()), Times.Once);
    }

    [Fact]
    public async Task ProcessMessagesAsync_WithCachedPaymentRequiredState_ThrowsPaymentRequiredAsync()
    {
        // Arrange
        var messages = new List<ChatMessage>
        {
            new (ChatRole.User, "Test message")
        };
        var settings = CreateValidPurviewSettings();
        var tokenInfo = new TokenInfo { TenantId = "tenant-123", UserId = "user-123", ClientId = "client-123" };
        this._mockPurviewClient.Setup(x => x.GetUserInfoFromTokenAsync(It.IsAny<CancellationToken>(), null))
            .ReturnsAsync(tokenInfo);

        this._mockCacheProvider.Setup(x => x.GetAsync<PaymentRequiredCacheKey, PaymentRequiredCacheEntry>(
            It.IsAny<PaymentRequiredCacheKey>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new PaymentRequiredCacheEntry("Payment required"));

        // Act + Assert
        await Assert.ThrowsAsync<PurviewPaymentRequiredException>(() =>
            this._processor.ProcessMessagesAsync(
                messages, "session-123", Activity.UploadText, settings, "user-123", CancellationToken.None));

        this._mockPurviewClient.Verify(x => x.ProcessContentAsync(
            It.IsAny<ProcessContentRequest>(), It.IsAny<CancellationToken>()), Times.Never);
        this._mockChannelHandler.Verify(x => x.QueueJob(It.IsAny<ScopeRetrievalJob>()), Times.Never);
    }

    [Fact]
    public async Task BackgroundJobRunner_ScopeRetrievalPaymentRequired_CachesForSubsequentCallsAsync()
    {
        // Arrange
        Func<Channel<BackgroundJobBase>, Task>? runner = null;
        Mock<IChannelHandler> channelHandler = new();
        Mock<IPurviewClient> purviewClient = new();
        Mock<ICacheProvider> cacheProvider = new();
        PurviewSettings settings = new("TestApp") { MaxConcurrentJobConsumers = 1 };
        ProtectionScopesRequest request = new("user-123", "tenant-123")
        {
            Activities = ProtectionScopeActivities.UploadText,
            Locations =
            [
                new("microsoft.graph.policyLocationApplication", "app-123")
            ]
        };
        ProtectionScopesCacheKey cacheKey = new(request);
        Channel<BackgroundJobBase> channel = Channel.CreateUnbounded<BackgroundJobBase>();

        channelHandler.Setup(x => x.AddRunner(It.IsAny<Func<Channel<BackgroundJobBase>, Task>>()))
            .Callback<Func<Channel<BackgroundJobBase>, Task>>(callback => runner = callback);

        purviewClient.Setup(x => x.GetProtectionScopesAsync(It.IsAny<ProtectionScopesRequest>(), It.IsAny<CancellationToken>()))
            .ThrowsAsync(new PurviewPaymentRequiredException("Payment required"));

        _ = new BackgroundJobRunner(channelHandler.Object, purviewClient.Object, cacheProvider.Object, NullLogger.Instance, settings);

        // Act
        Assert.NotNull(runner);
        await channel.Writer.WriteAsync(new ScopeRetrievalJob(request, cacheKey, CreateProcessContentRequest()));
        channel.Writer.Complete();
        await runner(channel);

        // Assert
        cacheProvider.Verify(x => x.SetAsync(
            It.Is<PaymentRequiredCacheKey>(key => key.TenantId == "tenant-123"),
            It.Is<PaymentRequiredCacheEntry>(entry => entry.Message == "Payment required"),
            It.IsAny<CancellationToken>()), Times.Once);
    }

    [Fact]
    public async Task BackgroundJobRunner_ScopeRetrievalCacheWriteFailure_DoesNotThrowAsync()
    {
        // Arrange
        Mock<IPurviewClient> purviewClient = new();
        Mock<ICacheProvider> cacheProvider = new();
        ProtectionScopesRequest request = CreateProtectionScopesRequest();
        ProtectionScopesCacheKey cacheKey = new(request);
        ScopeRetrievalJob job = new(request, cacheKey, CreateProcessContentRequest());

        purviewClient.Setup(x => x.GetProtectionScopesAsync(It.IsAny<ProtectionScopesRequest>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ProtectionScopesResponse());

        cacheProvider.Setup(x => x.SetAsync(
            It.IsAny<ProtectionScopesCacheKey>(),
            It.IsAny<ProtectionScopesResponse>(),
            It.IsAny<CancellationToken>()))
            .ThrowsAsync(new InvalidOperationException("cache unavailable"));

        // Act
        await RunBackgroundJobAsync(job, purviewClient.Object, cacheProvider.Object);

        // Assert
        purviewClient.Verify(x => x.GetProtectionScopesAsync(
            It.IsAny<ProtectionScopesRequest>(), It.IsAny<CancellationToken>()), Times.Once);
    }

    [Fact]
    public async Task BackgroundJobRunner_ScopeRetrievalNoApplicableScopes_QueuesContentActivityJobAsync()
    {
        // Arrange
        Func<Channel<BackgroundJobBase>, Task>? runner = null;
        Mock<IChannelHandler> channelHandler = new();
        Mock<IPurviewClient> purviewClient = new();
        Mock<ICacheProvider> cacheProvider = new();
        PurviewSettings settings = new("TestApp") { MaxConcurrentJobConsumers = 1 };
        ProtectionScopesRequest request = CreateProtectionScopesRequest();
        ScopeRetrievalJob job = new(request, new ProtectionScopesCacheKey(request), CreateProcessContentRequest());
        Channel<BackgroundJobBase> channel = Channel.CreateUnbounded<BackgroundJobBase>();

        channelHandler.Setup(x => x.AddRunner(It.IsAny<Func<Channel<BackgroundJobBase>, Task>>()))
            .Callback<Func<Channel<BackgroundJobBase>, Task>>(callback => runner = callback);

        purviewClient.Setup(x => x.GetProtectionScopesAsync(It.IsAny<ProtectionScopesRequest>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ProtectionScopesResponse { Scopes = [] });

        _ = new BackgroundJobRunner(channelHandler.Object, purviewClient.Object, cacheProvider.Object, NullLogger.Instance, settings);

        // Act
        Assert.NotNull(runner);
        await channel.Writer.WriteAsync(job);
        channel.Writer.Complete();
        await runner(channel);

        // Assert
        channelHandler.Verify(x => x.QueueJob(It.IsAny<ContentActivityJob>()), Times.Once);
    }

    [Fact]
    public async Task BackgroundJobRunner_ScopeRetrievalPaymentRequiredCacheWriteFailure_DoesNotThrowAsync()
    {
        // Arrange
        Mock<IPurviewClient> purviewClient = new();
        Mock<ICacheProvider> cacheProvider = new();
        ProtectionScopesRequest request = CreateProtectionScopesRequest();
        ScopeRetrievalJob job = new(request, new ProtectionScopesCacheKey(request), CreateProcessContentRequest());

        purviewClient.Setup(x => x.GetProtectionScopesAsync(It.IsAny<ProtectionScopesRequest>(), It.IsAny<CancellationToken>()))
            .ThrowsAsync(new PurviewPaymentRequiredException("Payment required"));

        cacheProvider.Setup(x => x.SetAsync(
            It.IsAny<PaymentRequiredCacheKey>(),
            It.IsAny<PaymentRequiredCacheEntry>(),
            It.IsAny<CancellationToken>()))
            .ThrowsAsync(new InvalidOperationException("cache unavailable"));

        // Act
        await RunBackgroundJobAsync(job, purviewClient.Object, cacheProvider.Object);

        // Assert
        cacheProvider.Verify(x => x.SetAsync(
            It.Is<PaymentRequiredCacheKey>(key => key.TenantId == "tenant-123"),
            It.Is<PaymentRequiredCacheEntry>(entry => entry.Message == "Payment required"),
            It.IsAny<CancellationToken>()), Times.Once);
    }

    #endregion

    #region Helper Methods

    private static ProtectionScopesRequest CreateProtectionScopesRequest()
    {
        return new ProtectionScopesRequest("user-123", "tenant-123")
        {
            Activities = ProtectionScopeActivities.UploadText,
            Locations =
            [
                new("microsoft.graph.policyLocationApplication", "app-123")
            ]
        };
    }

    private static ProcessContentRequest CreateProcessContentRequest()
    {
        PurviewTextContent content = new("Test content");
        ProcessConversationMetadata metadata = new(content, "msg-123", false, "Test message", "test-correlation-id");
        ActivityMetadata activityMetadata = new(Activity.UploadText);
        DeviceMetadata deviceMetadata = new()
        {
            OperatingSystemSpecifications = new()
            {
                OperatingSystemPlatform = "Windows",
                OperatingSystemVersion = "10"
            }
        };
        IntegratedAppMetadata integratedAppMetadata = new()
        {
            Name = "TestApp",
            Version = "1.0"
        };
        PolicyLocation policyLocation = new("microsoft.graph.policyLocationApplication", "app-123");
        ProtectedAppMetadata protectedAppMetadata = new(policyLocation)
        {
            Name = "TestApp",
            Version = "1.0"
        };
        ContentToProcess contentToProcess = new(
            [metadata],
            activityMetadata,
            deviceMetadata,
            integratedAppMetadata,
            protectedAppMetadata);

        return new ProcessContentRequest(contentToProcess, "user-123", "tenant-123");
    }

    private static async Task RunBackgroundJobAsync(BackgroundJobBase job, IPurviewClient purviewClient, ICacheProvider cacheProvider)
    {
        Func<Channel<BackgroundJobBase>, Task>? runner = null;
        Mock<IChannelHandler> channelHandler = new();
        PurviewSettings settings = new("TestApp") { MaxConcurrentJobConsumers = 1 };
        Channel<BackgroundJobBase> channel = Channel.CreateUnbounded<BackgroundJobBase>();

        channelHandler.Setup(x => x.AddRunner(It.IsAny<Func<Channel<BackgroundJobBase>, Task>>()))
            .Callback<Func<Channel<BackgroundJobBase>, Task>>(callback => runner = callback);

        _ = new BackgroundJobRunner(channelHandler.Object, purviewClient, cacheProvider, NullLogger.Instance, settings);

        Assert.NotNull(runner);
        await channel.Writer.WriteAsync(job);
        channel.Writer.Complete();
        await runner(channel);
    }

    private static PurviewSettings CreateValidPurviewSettings()
    {
        return new PurviewSettings("TestApp")
        {
            TenantId = "tenant-123",
            PurviewAppLocation = new PurviewAppLocation(PurviewLocationType.Application, "app-123")
        };
    }

    #endregion
}
