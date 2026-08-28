// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Purview.Models.Common;
using Microsoft.Agents.AI.Purview.Models.Jobs;
using Microsoft.Agents.AI.Purview.Models.Requests;
using Microsoft.Agents.AI.Purview.Models.Responses;
using Microsoft.Extensions.AI;
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
    public void CheckApplicableScopes_MatchesAnyLocationInScope()
    {
        // Arrange
        ProcessContentRequest pcRequest = CreateProcessContentRequest();
        ProtectionScopesResponse psResponse = new()
        {
            Scopes =
            [
                new()
                {
                    Activities = ProtectionScopeActivities.UploadText,
                    Locations =
                    [
                        new("microsoft.graph.policyLocationApplication", "app-123"),
                        new("microsoft.graph.policyLocationApplication", "different-app")
                    ],
                    ExecutionMode = ExecutionMode.EvaluateInline
                }
            ]
        };

        // Act
        (bool shouldProcess, _, ExecutionMode executionMode) = ScopedContentProcessor.CheckApplicableScopes(pcRequest, psResponse);

        // Assert
        Assert.True(shouldProcess);
        Assert.Equal(ExecutionMode.EvaluateInline, executionMode);
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
    public async Task ProcessMessagesAsync_MatchesAnyLocationInScope_WhenMatchingLocationFirstAsync()
    {
        // Arrange
        var messages = new List<ChatMessage>
        {
            new(ChatRole.User, "Test message")
        };
        var settings = CreateValidPurviewSettings();

        var psResponse = new ProtectionScopesResponse
        {
            Scopes =
            [
                new()
                {
                    Activities = ProtectionScopeActivities.UploadText,
                    Locations =
                    [
                        new("microsoft.graph.policyLocationApplication", "app-123"),
                        new("microsoft.graph.policyLocationApplication", "other-app-456")
                    ],
                    ExecutionMode = ExecutionMode.EvaluateInline,
                    PolicyActions =
                    [
                        new() { Action = DlpAction.BlockAccess }
                    ]
                }
            ]
        };

        this._mockCacheProvider.Setup(x => x.GetAsync<ProtectionScopesCacheKey, ProtectionScopesResponse>(
            It.IsAny<ProtectionScopesCacheKey>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(psResponse);

        this._mockPurviewClient.Setup(x => x.ProcessContentAsync(
            It.IsAny<ProcessContentRequest>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ProcessContentResponse { PolicyActions = [] });

        // Act
        var result = await this._processor.ProcessMessagesAsync(
            messages, "session-123", Activity.UploadText, settings, "user-123", CancellationToken.None);

        // Assert
        Assert.True(result.shouldBlock);
        this._mockPurviewClient.Verify(x => x.ProcessContentAsync(
            It.IsAny<ProcessContentRequest>(), It.IsAny<CancellationToken>()), Times.Once);
        this._mockChannelHandler.Verify(x => x.QueueJob(It.IsAny<ContentActivityJob>()), Times.Never);
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
        string userId = Guid.NewGuid().ToString();
        var messages = new List<ChatMessage>
        {
            new (ChatRole.User, "Test message")
            {
                AdditionalProperties = new AdditionalPropertiesDictionary
                {
                    { "userId", userId }
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
        Assert.Equal(userId, result.userId);
    }

    [Fact]
    public async Task ProcessMessagesAsync_IgnoresInvalidAdditionalPropertiesUserId_Async()
    {
        // Arrange
        var messages = new List<ChatMessage>
        {
            new(ChatRole.User, "Test message")
            {
                AdditionalProperties = new AdditionalPropertiesDictionary
                {
                    { "userId", "not-a-guid" }
                }
            }
        };
        var settings = CreateValidPurviewSettings();
        var tokenInfo = new TokenInfo { TenantId = "tenant-123", ClientId = "client-123" };

        this._mockPurviewClient.Setup(x => x.GetUserInfoFromTokenAsync(It.IsAny<CancellationToken>(), settings.TenantId))
            .ReturnsAsync(tokenInfo);

        // Act & Assert
        var exception = await Assert.ThrowsAsync<PurviewRequestException>(() =>
            this._processor.ProcessMessagesAsync(messages, "session-123", Activity.UploadText, settings, null, CancellationToken.None));

        Assert.Contains("No user id provided or inferred", exception.Message);
    }

    [Fact]
    public async Task ProcessMessagesAsync_UsesTokenUserIdBeforeMessageAdditionalProperties_Async()
    {
        // Arrange
        string tokenUserId = Guid.NewGuid().ToString();
        string messageUserId = Guid.NewGuid().ToString();
        var messages = new List<ChatMessage>
        {
            new(ChatRole.User, "Test message")
            {
                AdditionalProperties = new AdditionalPropertiesDictionary
                {
                    { "userId", messageUserId }
                }
            }
        };
        var settings = CreateValidPurviewSettings();
        var tokenInfo = new TokenInfo { TenantId = "tenant-123", UserId = tokenUserId, ClientId = "client-123" };

        this._mockPurviewClient.Setup(x => x.GetUserInfoFromTokenAsync(It.IsAny<CancellationToken>(), settings.TenantId))
            .ReturnsAsync(tokenInfo);

        this._mockCacheProvider.Setup(x => x.GetAsync<ProtectionScopesCacheKey, ProtectionScopesResponse>(
            It.IsAny<ProtectionScopesCacheKey>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync((ProtectionScopesResponse?)null);

        this._mockPurviewClient.Setup(x => x.GetProtectionScopesAsync(
            It.IsAny<ProtectionScopesRequest>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(CreateApplicableProtectionScopesResponse());
        this._mockPurviewClient.Setup(x => x.ProcessContentAsync(
            It.IsAny<ProcessContentRequest>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ProcessContentResponse { PolicyActions = [] });

        // Act
        var result = await this._processor.ProcessMessagesAsync(
            messages, "session-123", Activity.UploadText, settings, null, CancellationToken.None);

        // Assert
        Assert.Equal(tokenUserId, result.userId);
        this._mockPurviewClient.Verify(x => x.ProcessContentAsync(
            It.Is<ProcessContentRequest>(request => request.UserId == tokenUserId),
            It.IsAny<CancellationToken>()), Times.Once);
    }

    [Fact]
    public async Task ProcessMessagesAsync_UsesTokenUserIdBeforeAuthorName_Async()
    {
        // Arrange
        string tokenUserId = Guid.NewGuid().ToString();
        string authorUserId = Guid.NewGuid().ToString();
        var messages = new List<ChatMessage>
        {
            new(ChatRole.User, "Test message")
            {
                AuthorName = authorUserId
            }
        };
        var settings = CreateValidPurviewSettings();
        var tokenInfo = new TokenInfo { TenantId = "tenant-123", UserId = tokenUserId, ClientId = "client-123" };

        this._mockPurviewClient.Setup(x => x.GetUserInfoFromTokenAsync(It.IsAny<CancellationToken>(), settings.TenantId))
            .ReturnsAsync(tokenInfo);

        this._mockCacheProvider.Setup(x => x.GetAsync<ProtectionScopesCacheKey, ProtectionScopesResponse>(
            It.IsAny<ProtectionScopesCacheKey>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync((ProtectionScopesResponse?)null);

        this._mockPurviewClient.Setup(x => x.GetProtectionScopesAsync(
            It.IsAny<ProtectionScopesRequest>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(CreateApplicableProtectionScopesResponse());
        this._mockPurviewClient.Setup(x => x.ProcessContentAsync(
            It.IsAny<ProcessContentRequest>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ProcessContentResponse { PolicyActions = [] });

        // Act
        var result = await this._processor.ProcessMessagesAsync(
            messages, "session-123", Activity.UploadText, settings, null, CancellationToken.None);

        // Assert
        Assert.Equal(tokenUserId, result.userId);
        this._mockPurviewClient.Verify(x => x.ProcessContentAsync(
            It.Is<ProcessContentRequest>(request => request.UserId == tokenUserId),
            It.IsAny<CancellationToken>()), Times.Once);
    }

    [Fact]
    public async Task ProcessMessagesAsync_UsesProvidedUserId_WhenTokenUserIdIsEmptyAsync()
    {
        // Arrange
        string providedUserId = Guid.NewGuid().ToString();
        var messages = new List<ChatMessage>
        {
            new(ChatRole.User, "Test message")
        };
        var settings = CreateValidPurviewSettings();
        var tokenInfo = new TokenInfo { TenantId = "tenant-123", UserId = string.Empty, ClientId = "client-123" };

        this._mockPurviewClient.Setup(x => x.GetUserInfoFromTokenAsync(It.IsAny<CancellationToken>(), settings.TenantId))
            .ReturnsAsync(tokenInfo);

        this._mockCacheProvider.Setup(x => x.GetAsync<ProtectionScopesCacheKey, ProtectionScopesResponse>(
            It.IsAny<ProtectionScopesCacheKey>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync((ProtectionScopesResponse?)null);

        this._mockPurviewClient.Setup(x => x.GetProtectionScopesAsync(
            It.IsAny<ProtectionScopesRequest>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(CreateApplicableProtectionScopesResponse());
        this._mockPurviewClient.Setup(x => x.ProcessContentAsync(
            It.IsAny<ProcessContentRequest>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ProcessContentResponse { PolicyActions = [] });

        // Act
        var result = await this._processor.ProcessMessagesAsync(
            messages, "session-123", Activity.UploadText, settings, providedUserId, CancellationToken.None);

        // Assert
        Assert.Equal(providedUserId, result.userId);
        this._mockPurviewClient.Verify(x => x.ProcessContentAsync(
            It.Is<ProcessContentRequest>(request => request.UserId == providedUserId),
            It.IsAny<CancellationToken>()), Times.Once);
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
    public async Task ProcessMessagesAsync_CacheMiss_RetrievesScopesBeforeInlineProcessingAsync()
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

        ProtectionScopesResponse scopes = CreateApplicableProtectionScopesResponse();
        this._mockPurviewClient.Setup(x => x.GetProtectionScopesAsync(
            It.IsAny<ProtectionScopesRequest>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(scopes);

        this._mockPurviewClient.Setup(x => x.ProcessContentAsync(
            It.Is<ProcessContentRequest>(request =>
                request.ScopeIdentifier == scopes.ScopeIdentifier &&
                request.ProcessInline),
            It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ProcessContentResponse
            {
                PolicyActions =
                [
                    new() { Action = DlpAction.BlockAccess }
                ]
            });

        // Act
        var result = await this._processor.ProcessMessagesAsync(
            messages, "session-123", Activity.UploadText, settings, "user-123", CancellationToken.None);

        // Assert
        Assert.True(result.shouldBlock);
        this._mockPurviewClient.Verify(x => x.GetProtectionScopesAsync(
            It.IsAny<ProtectionScopesRequest>(), It.IsAny<CancellationToken>()), Times.Once);
        this._mockCacheProvider.Verify(x => x.SetAsync(
            It.IsAny<ProtectionScopesCacheKey>(), scopes, It.IsAny<CancellationToken>()), Times.Once);
        this._mockPurviewClient.Verify(x => x.ProcessContentAsync(
            It.Is<ProcessContentRequest>(request =>
                request.ScopeIdentifier == scopes.ScopeIdentifier &&
                request.ProcessInline),
            It.IsAny<CancellationToken>()), Times.Once);
    }

    [Fact]
    public async Task ProcessMessagesAsync_CacheMiss_WithOfflineScope_QueuesScopedProcessContentAsync()
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

        ProtectionScopesResponse scopes = CreateApplicableProtectionScopesResponse(ExecutionMode.EvaluateOffline);
        this._mockPurviewClient.Setup(x => x.GetProtectionScopesAsync(
            It.IsAny<ProtectionScopesRequest>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(scopes);

        // Act
        await this._processor.ProcessMessagesAsync(
            messages, "session-123", Activity.UploadText, settings, "user-123", CancellationToken.None);

        // Assert
        this._mockPurviewClient.Verify(x => x.ProcessContentAsync(
            It.IsAny<ProcessContentRequest>(), It.IsAny<CancellationToken>()), Times.Never);
        this._mockChannelHandler.Verify(x => x.QueueJob(
            It.Is<ProcessContentJob>(job =>
                job.Request.ScopeIdentifier == scopes.ScopeIdentifier &&
                !job.Request.ProcessInline)), Times.Once);
    }

    [Fact]
    public async Task ProcessMessagesAsync_CacheMiss_WithNoApplicableScope_QueuesContentActivityAsync()
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

        this._mockPurviewClient.Setup(x => x.GetProtectionScopesAsync(
            It.IsAny<ProtectionScopesRequest>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ProtectionScopesResponse { ScopeIdentifier = "scope-123", Scopes = [] });

        // Act
        await this._processor.ProcessMessagesAsync(
            messages, "session-123", Activity.UploadText, settings, "user-123", CancellationToken.None);

        // Assert
        this._mockPurviewClient.Verify(x => x.ProcessContentAsync(
            It.IsAny<ProcessContentRequest>(), It.IsAny<CancellationToken>()), Times.Never);
        this._mockChannelHandler.Verify(x => x.QueueJob(It.IsAny<ContentActivityJob>()), Times.Once);
    }

    [Fact]
    public async Task ProcessMessagesAsync_CacheMiss_WhenScopeRetrievalFails_DoesNotProcessContentAsync()
    {
        // Arrange
        var messages = new List<ChatMessage>
        {
            new(ChatRole.User, "Test message")
        };
        var settings = CreateValidPurviewSettings();
        var tokenInfo = new TokenInfo { TenantId = "tenant-123", UserId = "user-123", ClientId = "client-123" };
        this._mockPurviewClient.Setup(x => x.GetUserInfoFromTokenAsync(It.IsAny<CancellationToken>(), null))
            .ReturnsAsync(tokenInfo);
        this._mockCacheProvider.Setup(x => x.GetAsync<ProtectionScopesCacheKey, ProtectionScopesResponse>(
            It.IsAny<ProtectionScopesCacheKey>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync((ProtectionScopesResponse?)null);
        this._mockPurviewClient.Setup(x => x.GetProtectionScopesAsync(
            It.IsAny<ProtectionScopesRequest>(), It.IsAny<CancellationToken>()))
            .ThrowsAsync(new PurviewRequestException("scope retrieval failed"));

        // Act & Assert
        await Assert.ThrowsAsync<PurviewRequestException>(() =>
            this._processor.ProcessMessagesAsync(
                messages, "session-123", Activity.UploadText, settings, "user-123", CancellationToken.None));
        this._mockPurviewClient.Verify(x => x.ProcessContentAsync(
            It.IsAny<ProcessContentRequest>(), It.IsAny<CancellationToken>()), Times.Never);
        this._mockChannelHandler.Verify(x => x.QueueJob(It.IsAny<BackgroundJobBase>()), Times.Never);
    }

    [Fact]
    public async Task ProcessMessagesAsync_CacheMiss_WhenScopeCachingFails_DoesNotProcessContentAsync()
    {
        // Arrange
        var messages = new List<ChatMessage>
        {
            new(ChatRole.User, "Test message")
        };
        var settings = CreateValidPurviewSettings();
        var tokenInfo = new TokenInfo { TenantId = "tenant-123", UserId = "user-123", ClientId = "client-123" };
        ProtectionScopesResponse scopes = CreateApplicableProtectionScopesResponse();
        this._mockPurviewClient.Setup(x => x.GetUserInfoFromTokenAsync(It.IsAny<CancellationToken>(), null))
            .ReturnsAsync(tokenInfo);
        this._mockCacheProvider.Setup(x => x.GetAsync<ProtectionScopesCacheKey, ProtectionScopesResponse>(
            It.IsAny<ProtectionScopesCacheKey>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync((ProtectionScopesResponse?)null);
        this._mockPurviewClient.Setup(x => x.GetProtectionScopesAsync(
            It.IsAny<ProtectionScopesRequest>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(scopes);
        this._mockCacheProvider.Setup(x => x.SetAsync(
            It.IsAny<ProtectionScopesCacheKey>(), scopes, It.IsAny<CancellationToken>()))
            .ThrowsAsync(new PurviewRequestException("scope caching failed"));

        // Act & Assert
        await Assert.ThrowsAsync<PurviewRequestException>(() =>
            this._processor.ProcessMessagesAsync(
                messages, "session-123", Activity.UploadText, settings, "user-123", CancellationToken.None));
        this._mockPurviewClient.Verify(x => x.ProcessContentAsync(
            It.IsAny<ProcessContentRequest>(), It.IsAny<CancellationToken>()), Times.Never);
        this._mockChannelHandler.Verify(x => x.QueueJob(It.IsAny<BackgroundJobBase>()), Times.Never);
    }

    [Fact]
    public async Task ProcessMessagesAsync_CacheMiss_WhenScopeRetrievalIsCanceled_DoesNotProcessContentAsync()
    {
        // Arrange
        var messages = new List<ChatMessage>
        {
            new(ChatRole.User, "Test message")
        };
        var settings = CreateValidPurviewSettings();
        var tokenInfo = new TokenInfo { TenantId = "tenant-123", UserId = "user-123", ClientId = "client-123" };
        this._mockPurviewClient.Setup(x => x.GetUserInfoFromTokenAsync(It.IsAny<CancellationToken>(), null))
            .ReturnsAsync(tokenInfo);
        this._mockCacheProvider.Setup(x => x.GetAsync<ProtectionScopesCacheKey, ProtectionScopesResponse>(
            It.IsAny<ProtectionScopesCacheKey>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync((ProtectionScopesResponse?)null);
        this._mockPurviewClient.Setup(x => x.GetProtectionScopesAsync(
            It.IsAny<ProtectionScopesRequest>(), It.IsAny<CancellationToken>()))
            .ThrowsAsync(new OperationCanceledException());

        // Act & Assert
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() =>
            this._processor.ProcessMessagesAsync(
                messages, "session-123", Activity.UploadText, settings, "user-123", CancellationToken.None));
        this._mockPurviewClient.Verify(x => x.ProcessContentAsync(
            It.IsAny<ProcessContentRequest>(), It.IsAny<CancellationToken>()), Times.Never);
        this._mockChannelHandler.Verify(x => x.QueueJob(It.IsAny<BackgroundJobBase>()), Times.Never);
    }

    [Fact]
    public async Task ProcessMessagesAsync_CacheMiss_WhenPaymentIsRequired_CachesAndRethrowsAsync()
    {
        // Arrange
        var messages = new List<ChatMessage>
        {
            new(ChatRole.User, "Test message")
        };
        var settings = CreateValidPurviewSettings();
        var tokenInfo = new TokenInfo { TenantId = "tenant-123", UserId = "user-123", ClientId = "client-123" };
        this._mockPurviewClient.Setup(x => x.GetUserInfoFromTokenAsync(It.IsAny<CancellationToken>(), null))
            .ReturnsAsync(tokenInfo);
        this._mockCacheProvider.Setup(x => x.GetAsync<ProtectionScopesCacheKey, ProtectionScopesResponse>(
            It.IsAny<ProtectionScopesCacheKey>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync((ProtectionScopesResponse?)null);
        this._mockPurviewClient.Setup(x => x.GetProtectionScopesAsync(
            It.IsAny<ProtectionScopesRequest>(), It.IsAny<CancellationToken>()))
            .ThrowsAsync(new PurviewPaymentRequiredException("Payment required"));

        // Act & Assert
        await Assert.ThrowsAsync<PurviewPaymentRequiredException>(() =>
            this._processor.ProcessMessagesAsync(
                messages, "session-123", Activity.UploadText, settings, "user-123", CancellationToken.None));
        this._mockCacheProvider.Verify(x => x.SetAsync(
            It.Is<PaymentRequiredCacheKey>(key => key.TenantId == "tenant-123"),
            It.Is<PaymentRequiredCacheEntry>(entry => entry.Message == "Payment required"),
            It.IsAny<CancellationToken>()), Times.Once);
        this._mockPurviewClient.Verify(x => x.ProcessContentAsync(
            It.IsAny<ProcessContentRequest>(), It.IsAny<CancellationToken>()), Times.Never);
    }

    [Fact]
    public async Task ProcessMessagesAsync_ConcurrentCacheMisses_ShareScopeRetrievalAsync()
    {
        // Arrange
        var messages = new List<ChatMessage>
        {
            new(ChatRole.User, "Test message")
        };
        var settings = CreateValidPurviewSettings();
        var tokenInfo = new TokenInfo { TenantId = "tenant-123", UserId = "user-123", ClientId = "client-123" };
        TaskCompletionSource<ProtectionScopesResponse> scopesSource = new(TaskCreationOptions.RunContinuationsAsynchronously);
        TaskCompletionSource<bool> retrievalStarted = new(TaskCreationOptions.RunContinuationsAsynchronously);
        TaskCompletionSource<bool> secondCacheRead = new(TaskCreationOptions.RunContinuationsAsynchronously);
        int cacheReadCount = 0;

        this._mockPurviewClient.Setup(x => x.GetUserInfoFromTokenAsync(It.IsAny<CancellationToken>(), null))
            .ReturnsAsync(tokenInfo);
        this._mockCacheProvider.Setup(x => x.GetAsync<ProtectionScopesCacheKey, ProtectionScopesResponse>(
            It.IsAny<ProtectionScopesCacheKey>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(() =>
            {
                if (Interlocked.Increment(ref cacheReadCount) == 2)
                {
                    secondCacheRead.TrySetResult(true);
                }

                return null;
            });
        this._mockPurviewClient.Setup(x => x.GetProtectionScopesAsync(
            It.IsAny<ProtectionScopesRequest>(), It.IsAny<CancellationToken>()))
            .Returns(() =>
            {
                retrievalStarted.TrySetResult(true);
                return scopesSource.Task;
            });
        this._mockPurviewClient.Setup(x => x.ProcessContentAsync(
            It.IsAny<ProcessContentRequest>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ProcessContentResponse());

        Task<(bool shouldBlock, string? userId)> first = this._processor.ProcessMessagesAsync(
            messages, "session-123", Activity.UploadText, settings, "user-123", CancellationToken.None);
        await retrievalStarted.Task;
        Task<(bool shouldBlock, string? userId)> second = this._processor.ProcessMessagesAsync(
            messages, "session-456", Activity.UploadText, settings, "user-123", CancellationToken.None);
        await secondCacheRead.Task;

        // Act
        scopesSource.SetResult(CreateApplicableProtectionScopesResponse());
        await Task.WhenAll(first, second);

        // Assert
        this._mockPurviewClient.Verify(x => x.GetProtectionScopesAsync(
            It.IsAny<ProtectionScopesRequest>(), It.IsAny<CancellationToken>()), Times.Once);
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
        this._mockChannelHandler.Verify(x => x.QueueJob(It.IsAny<BackgroundJobBase>()), Times.Never);
    }

    #endregion

    #region Helper Methods

    private static ProtectionScopesResponse CreateApplicableProtectionScopesResponse(ExecutionMode executionMode = ExecutionMode.EvaluateInline)
    {
        return new ProtectionScopesResponse
        {
            ScopeIdentifier = "scope-123",
            Scopes =
            [
                new()
                {
                    Activities = ProtectionScopeActivities.UploadText,
                    Locations =
                    [
                        new("microsoft.graph.policyLocationApplication", "app-123")
                    ],
                    ExecutionMode = executionMode
                }
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
