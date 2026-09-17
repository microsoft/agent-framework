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
    public void CheckApplicableScopes_MatchesUrlLocationHostCaseInsensitively()
    {
        // Arrange
        ProcessContentRequest pcRequest = CreateProcessContentRequest();
        pcRequest.ContentToProcess.ProtectedAppMetadata.ApplicationLocation =
            new("microsoft.graph.policyLocationUrl", "HTTPS://Contoso.com/sites/marketing");
        ProtectionScopesResponse psResponse = new()
        {
            Scopes =
            [
                new()
                {
                    Activities = ProtectionScopeActivities.UploadText,
                    Locations = [new("#microsoft.graph.policyLocationUrl", "https://contoso.com/sites/marketing")],
                    ExecutionMode = ExecutionMode.EvaluateInline
                }
            ]
        };

        // Act
        (bool shouldProcess, _, _) = ScopedContentProcessor.CheckApplicableScopes(pcRequest, psResponse);

        // Assert
        Assert.True(shouldProcess);
    }

    [Fact]
    public void CheckApplicableScopes_TreatsUrlLocationPathAsCaseSensitive()
    {
        // Arrange
        ProcessContentRequest pcRequest = CreateProcessContentRequest();
        pcRequest.ContentToProcess.ProtectedAppMetadata.ApplicationLocation =
            new("microsoft.graph.policyLocationUrl", "https://contoso.com/sites/Marketing");
        ProtectionScopesResponse psResponse = new()
        {
            Scopes =
            [
                new()
                {
                    Activities = ProtectionScopeActivities.UploadText,
                    Locations = [new("#microsoft.graph.policyLocationUrl", "https://contoso.com/sites/marketing")],
                    ExecutionMode = ExecutionMode.EvaluateInline
                }
            ]
        };

        // Act
        (bool shouldProcess, List<DlpActionInfo> dlpActions, _) = ScopedContentProcessor.CheckApplicableScopes(pcRequest, psResponse);

        // Assert
        Assert.False(shouldProcess);
        Assert.Empty(dlpActions);
    }

    [Fact]
    public void CheckApplicableScopes_TreatsUrlLocationQueryAsCaseSensitive()
    {
        // Arrange
        ProcessContentRequest pcRequest = CreateProcessContentRequest();
        pcRequest.ContentToProcess.ProtectedAppMetadata.ApplicationLocation =
            new("microsoft.graph.policyLocationUrl", "https://contoso.com?label=Secret");
        ProtectionScopesResponse psResponse = new()
        {
            Scopes =
            [
                new()
                {
                    Activities = ProtectionScopeActivities.UploadText,
                    Locations = [new("#microsoft.graph.policyLocationUrl", "https://contoso.com?label=secret")],
                    ExecutionMode = ExecutionMode.EvaluateInline
                }
            ]
        };

        // Act
        (bool shouldProcess, List<DlpActionInfo> dlpActions, _) = ScopedContentProcessor.CheckApplicableScopes(pcRequest, psResponse);

        // Assert
        Assert.False(shouldProcess);
        Assert.Empty(dlpActions);
    }

    [Fact]
    public void CheckApplicableScopes_TreatsUrlLocationFragmentAsCaseSensitive()
    {
        // Arrange
        ProcessContentRequest pcRequest = CreateProcessContentRequest();
        pcRequest.ContentToProcess.ProtectedAppMetadata.ApplicationLocation =
            new("microsoft.graph.policyLocationUrl", "https://contoso.com#Section");
        ProtectionScopesResponse psResponse = new()
        {
            Scopes =
            [
                new()
                {
                    Activities = ProtectionScopeActivities.UploadText,
                    Locations = [new("#microsoft.graph.policyLocationUrl", "https://contoso.com#section")],
                    ExecutionMode = ExecutionMode.EvaluateInline
                }
            ]
        };

        // Act
        (bool shouldProcess, List<DlpActionInfo> dlpActions, _) = ScopedContentProcessor.CheckApplicableScopes(pcRequest, psResponse);

        // Assert
        Assert.False(shouldProcess);
        Assert.Empty(dlpActions);
    }

    [Fact]
    public void CheckApplicableScopes_TreatsUrlLocationUserInfoAsCaseSensitive()
    {
        // Arrange
        ProcessContentRequest pcRequest = CreateProcessContentRequest();
        pcRequest.ContentToProcess.ProtectedAppMetadata.ApplicationLocation =
            new("microsoft.graph.policyLocationUrl", "https://alice:SecretPass@contoso.com/docs");
        ProtectionScopesResponse psResponse = new()
        {
            Scopes =
            [
                new()
                {
                    Activities = ProtectionScopeActivities.UploadText,
                    Locations = [new("#microsoft.graph.policyLocationUrl", "https://alice:secretpass@contoso.com/docs")],
                    ExecutionMode = ExecutionMode.EvaluateInline
                }
            ]
        };

        // Act
        (bool shouldProcess, List<DlpActionInfo> dlpActions, _) = ScopedContentProcessor.CheckApplicableScopes(pcRequest, psResponse);

        // Assert
        Assert.False(shouldProcess);
        Assert.Empty(dlpActions);
    }

    [Fact]
    public void CheckApplicableScopes_MatchesApplicationLocationCaseInsensitively()
    {
        // Arrange
        ProcessContentRequest pcRequest = CreateProcessContentRequest();
        pcRequest.ContentToProcess.ProtectedAppMetadata.ApplicationLocation =
            new("microsoft.graph.policyLocationApplication", "A1B2C3D4-E5F6-4A5B-8C9D-0E1F2A3B4C5D");
        ProtectionScopesResponse psResponse = new()
        {
            Scopes =
            [
                new()
                {
                    Activities = ProtectionScopeActivities.UploadText,
                    Locations =
                    [
                        new("#microsoft.graph.policyLocationApplication", "a1b2c3d4-e5f6-4a5b-8c9d-0e1f2a3b4c5d")
                    ],
                    ExecutionMode = ExecutionMode.EvaluateInline
                }
            ]
        };

        // Act
        (bool shouldProcess, _, _) = ScopedContentProcessor.CheckApplicableScopes(pcRequest, psResponse);

        // Assert
        Assert.True(shouldProcess);
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
    public async Task ProcessMessagesAsync_CacheMiss_CallsProcessContentInlineAndQueuesScopeRetrievalAsync()
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
            It.Is<ProcessContentRequest>(request =>
                request.ScopeIdentifier == null &&
                request.ProcessInline),
            It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ProcessContentResponse());

        // Act
        await this._processor.ProcessMessagesAsync(
            messages, "session-123", Activity.UploadText, settings, "user-123", CancellationToken.None);

        // Assert
        this._mockPurviewClient.Verify(x => x.ProcessContentAsync(
            It.Is<ProcessContentRequest>(request =>
                request.ScopeIdentifier == null &&
                request.ProcessInline),
            It.IsAny<CancellationToken>()), Times.Once);
        this._mockPurviewClient.Verify(x => x.GetProtectionScopesAsync(
            It.IsAny<ProtectionScopesRequest>(), It.IsAny<CancellationToken>()), Times.Never);
        this._mockChannelHandler.Verify(x => x.QueueJob(
            It.Is<ScopeRetrievalJob>(job => job.ProcessContentRequest.ProcessInline)), Times.Once);
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

        this._mockPurviewClient.Setup(x => x.ProcessContentAsync(
            It.Is<ProcessContentRequest>(request => request.ProcessInline),
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
        this._mockPurviewClient.Verify(x => x.ProcessContentAsync(
            It.Is<ProcessContentRequest>(request => request.ProcessInline),
            It.IsAny<CancellationToken>()), Times.Once);
    }

    [Fact]
    public async Task ProcessMessagesAsync_CacheMiss_WhenScopeRetrievalCannotQueue_CallsProcessContentInlineAsync()
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
            It.Is<ProcessContentRequest>(request => request.ProcessInline),
            It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ProcessContentResponse());

        // Act
        await this._processor.ProcessMessagesAsync(
            messages, "session-123", Activity.UploadText, settings, "user-123", CancellationToken.None);

        // Assert
        this._mockChannelHandler.Verify(x => x.QueueJob(It.IsAny<ScopeRetrievalJob>()), Times.Once);
        this._mockPurviewClient.Verify(x => x.ProcessContentAsync(
            It.Is<ProcessContentRequest>(request => request.ProcessInline),
            It.IsAny<CancellationToken>()), Times.Once);
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

    [Fact]
    public async Task BackgroundJobRunner_ScopeRetrievalNoApplicableScopes_CachesAndQueuesContentActivityAsync()
    {
        // Arrange
        Func<Channel<BackgroundJobBase>, Task>? runner = null;
        Mock<IChannelHandler> channelHandler = new();
        Mock<IPurviewClient> purviewClient = new();
        Mock<ICacheProvider> cacheProvider = new();
        PurviewSettings settings = new("TestApp") { MaxConcurrentJobConsumers = 1 };
        ProtectionScopesRequest request = CreateProtectionScopesRequest();
        ProtectionScopesCacheKey cacheKey = new(request);
        ScopeRetrievalJob job = new(request, cacheKey, CreateProcessContentRequest());
        ProtectionScopesResponse response = new() { ScopeIdentifier = "scope-123", Scopes = [] };
        Channel<BackgroundJobBase> channel = Channel.CreateUnbounded<BackgroundJobBase>();

        channelHandler.Setup(x => x.AddRunner(It.IsAny<Func<Channel<BackgroundJobBase>, Task>>()))
            .Callback<Func<Channel<BackgroundJobBase>, Task>>(callback => runner = callback);
        purviewClient.Setup(x => x.GetProtectionScopesAsync(It.IsAny<ProtectionScopesRequest>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(response);

        _ = new BackgroundJobRunner(channelHandler.Object, purviewClient.Object, cacheProvider.Object, NullLogger.Instance, settings);

        // Act
        Assert.NotNull(runner);
        await channel.Writer.WriteAsync(job);
        channel.Writer.Complete();
        await runner(channel);

        // Assert
        cacheProvider.Verify(x => x.SetAsync(cacheKey, response, It.IsAny<CancellationToken>()), Times.Once);
        channelHandler.Verify(x => x.QueueJob(It.IsAny<ContentActivityJob>()), Times.Once);
    }

    [Fact]
    public async Task BackgroundJobRunner_ScopeRetrievalApplicableScope_CachesWithoutContentActivityAsync()
    {
        // Arrange
        Func<Channel<BackgroundJobBase>, Task>? runner = null;
        Mock<IChannelHandler> channelHandler = new();
        Mock<IPurviewClient> purviewClient = new();
        Mock<ICacheProvider> cacheProvider = new();
        PurviewSettings settings = new("TestApp") { MaxConcurrentJobConsumers = 1 };
        ProtectionScopesRequest request = CreateProtectionScopesRequest();
        ProtectionScopesCacheKey cacheKey = new(request);
        ScopeRetrievalJob job = new(request, cacheKey, CreateProcessContentRequest());
        ProtectionScopesResponse response = CreateApplicableProtectionScopesResponse();
        Channel<BackgroundJobBase> channel = Channel.CreateUnbounded<BackgroundJobBase>();

        channelHandler.Setup(x => x.AddRunner(It.IsAny<Func<Channel<BackgroundJobBase>, Task>>()))
            .Callback<Func<Channel<BackgroundJobBase>, Task>>(callback => runner = callback);
        purviewClient.Setup(x => x.GetProtectionScopesAsync(It.IsAny<ProtectionScopesRequest>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(response);

        _ = new BackgroundJobRunner(channelHandler.Object, purviewClient.Object, cacheProvider.Object, NullLogger.Instance, settings);

        // Act
        Assert.NotNull(runner);
        await channel.Writer.WriteAsync(job);
        channel.Writer.Complete();
        await runner(channel);

        // Assert
        cacheProvider.Verify(x => x.SetAsync(cacheKey, response, It.IsAny<CancellationToken>()), Times.Once);
        channelHandler.Verify(x => x.QueueJob(It.IsAny<ContentActivityJob>()), Times.Never);
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
        ProtectionScopesRequest request = CreateProtectionScopesRequest();
        ScopeRetrievalJob job = new(request, new ProtectionScopesCacheKey(request), CreateProcessContentRequest());
        Channel<BackgroundJobBase> channel = Channel.CreateUnbounded<BackgroundJobBase>();

        channelHandler.Setup(x => x.AddRunner(It.IsAny<Func<Channel<BackgroundJobBase>, Task>>()))
            .Callback<Func<Channel<BackgroundJobBase>, Task>>(callback => runner = callback);
        purviewClient.Setup(x => x.GetProtectionScopesAsync(It.IsAny<ProtectionScopesRequest>(), It.IsAny<CancellationToken>()))
            .ThrowsAsync(new PurviewPaymentRequiredException("Payment required"));

        _ = new BackgroundJobRunner(channelHandler.Object, purviewClient.Object, cacheProvider.Object, NullLogger.Instance, settings);

        // Act
        Assert.NotNull(runner);
        await channel.Writer.WriteAsync(job);
        channel.Writer.Complete();
        await runner(channel);

        // Assert
        cacheProvider.Verify(x => x.SetAsync(
            It.Is<PaymentRequiredCacheKey>(key => key.TenantId == "tenant-123"),
            It.Is<PaymentRequiredCacheEntry>(entry => entry.Message == "Payment required"),
            It.IsAny<CancellationToken>()), Times.Once);
    }

    /// <summary>
    /// Verifies every content item is submitted for evaluation in a separate request, not just <c>message.Text</c>.
    /// Images, binary payloads and structured tool results are empty when flattened to text, which
    /// would have them reach the model having only ever been classified as an empty string.
    /// </summary>
    [Fact]
    public async Task ProcessMessagesAsync_WithMultipleContentItems_SubmitsEachInSeparateRequestAsync()
    {
        // Arrange
        byte[] secret = [0x01, 0x02, 0x03, 0x04];
        var messages = new List<ChatMessage>
        {
            new(ChatRole.User,
            [
                new DataContent(secret, "application/octet-stream"),
                new FunctionCallContent("call-1", "exfiltrate", new Dictionary<string, object?> { ["ssn"] = "123-45-6789" })
            ])
        };
        var settings = CreateValidPurviewSettings();
        var tokenInfo = new TokenInfo { TenantId = "tenant-123", UserId = "user-123", ClientId = "client-123" };

        this._mockPurviewClient.Setup(x => x.GetUserInfoFromTokenAsync(It.IsAny<CancellationToken>(), null))
            .ReturnsAsync(tokenInfo);
        this._mockCacheProvider.Setup(x => x.GetAsync<ProtectionScopesCacheKey, ProtectionScopesResponse>(
            It.IsAny<ProtectionScopesCacheKey>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(CreateApplicableProtectionScopesResponse());

        List<ProcessContentRequest> capturedRequests = [];
        this._mockPurviewClient.Setup(x => x.ProcessContentAsync(
            It.IsAny<ProcessContentRequest>(), It.IsAny<CancellationToken>()))
            .Callback<ProcessContentRequest, CancellationToken>((request, _) => capturedRequests.Add(request))
            .ReturnsAsync(new ProcessContentResponse());

        // Act
        await this._processor.ProcessMessagesAsync(
            messages, "session-123", Activity.UploadText, settings, "user-123", CancellationToken.None);

        // Assert
        Assert.Equal(2, capturedRequests.Count);
        ProcessContentMetadataBase binaryEntry = Assert.Single(capturedRequests[0].ContentToProcess.ContentEntries);
        ProcessContentMetadataBase functionCallEntry = Assert.Single(capturedRequests[1].ContentToProcess.ContentEntries);

        PurviewBinaryContent binaryContent = Assert.IsType<PurviewBinaryContent>(binaryEntry.Content);
        Assert.Equal(secret, binaryContent.Data);

        PurviewTextContent functionCallContent = Assert.IsType<PurviewTextContent>(functionCallEntry.Content);
        Assert.Contains("123-45-6789", functionCallContent.Data, StringComparison.Ordinal);

        // Content entries must be individually addressable, not collapsed onto one identifier.
        Assert.NotEqual(binaryEntry.Identifier, functionCallEntry.Identifier);
    }

    [Fact]
    public async Task ProcessMessagesAsync_WithEmptyTextAndData_SkipsEmptyContentAsync()
    {
        // Arrange
        byte[] emptyData = [];
        List<ChatMessage> messages =
        [
            new(ChatRole.User,
            [
                new TextContent(string.Empty),
                new DataContent(emptyData, "application/octet-stream")
            ])
        ];
        PurviewSettings settings = CreateValidPurviewSettings();
        TokenInfo tokenInfo = new() { TenantId = "tenant-123", UserId = "user-123", ClientId = "client-123" };

        this._mockPurviewClient.Setup(x => x.GetUserInfoFromTokenAsync(It.IsAny<CancellationToken>(), null))
            .ReturnsAsync(tokenInfo);

        // Act
        await this._processor.ProcessMessagesAsync(
            messages, "session-123", Activity.UploadText, settings, "user-123", CancellationToken.None);

        // Assert
        this._mockPurviewClient.Verify(x => x.ProcessContentAsync(
            It.IsAny<ProcessContentRequest>(), It.IsAny<CancellationToken>()), Times.Never);
    }

    /// <summary>
    /// Verifies a block verdict known from an offline cached scope is still enforced. The offline
    /// branch reports asynchronously, but discarding the scope's own policy actions would let a
    /// known <c>restrictAccess</c> verdict go unenforced.
    /// </summary>
    [Fact]
    public async Task ProcessMessagesAsync_WithOfflineScopeCarryingBlockAction_ReturnsShouldBlockTrueAsync()
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
                    ExecutionMode = ExecutionMode.EvaluateOffline,
                    PolicyActions =
                    [
                        new() { Action = DlpAction.RestrictAccess, RestrictionAction = RestrictionAction.Block }
                    ]
                }
            ]
        };

        this._mockCacheProvider.Setup(x => x.GetAsync<ProtectionScopesCacheKey, ProtectionScopesResponse>(
            It.IsAny<ProtectionScopesCacheKey>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(psResponse);

        // Act
        var result = await this._processor.ProcessMessagesAsync(
            messages, "session-123", Activity.UploadText, settings, "user-123", CancellationToken.None);

        // Assert
        Assert.True(result.shouldBlock);

        // The offline report is still queued; enforcement is additional, not a replacement.
        this._mockChannelHandler.Verify(x => x.QueueJob(It.IsAny<ProcessContentJob>()), Times.Once);
    }

    /// <summary>
    /// Verifies a <c>restrictAccess</c> scope whose restriction mode does not block is not enforced as
    /// a block. The action carries a separate <see cref="RestrictionAction"/> that may be
    /// <see cref="RestrictionAction.Audit"/>, <see cref="RestrictionAction.Warn"/> or
    /// <see cref="RestrictionAction.Allow"/>, none of which withhold the content.
    /// </summary>
    [Fact]
    public async Task ProcessMessagesAsync_WithOfflineScopeCarryingAuditRestriction_ReturnsShouldBlockFalseAsync()
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
                    ExecutionMode = ExecutionMode.EvaluateOffline,
                    PolicyActions =
                    [
                        new() { Action = DlpAction.RestrictAccess, RestrictionAction = RestrictionAction.Audit }
                    ]
                }
            ]
        };

        this._mockCacheProvider.Setup(x => x.GetAsync<ProtectionScopesCacheKey, ProtectionScopesResponse>(
            It.IsAny<ProtectionScopesCacheKey>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(psResponse);

        // Act
        var result = await this._processor.ProcessMessagesAsync(
            messages, "session-123", Activity.UploadText, settings, "user-123", CancellationToken.None);

        // Assert
        Assert.False(result.shouldBlock);

        // The offline report is still queued so the audit action is recorded.
        this._mockChannelHandler.Verify(x => x.QueueJob(It.IsAny<ProcessContentJob>()), Times.Once);
    }

    /// <summary>
    /// Verifies an unrecognised <see cref="ExecutionMode"/> is evaluated inline. The enum is
    /// evolvable, so an unknown member must not be treated as permission to skip enforcement.
    /// </summary>
    [Fact]
    public async Task ProcessMessagesAsync_WithUnknownExecutionMode_EvaluatesInlineAsync()
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
            .ReturnsAsync(CreateApplicableProtectionScopesResponse((ExecutionMode)9999));

        this._mockPurviewClient.Setup(x => x.ProcessContentAsync(
            It.IsAny<ProcessContentRequest>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ProcessContentResponse
            {
                PolicyActions = [new() { Action = DlpAction.BlockAccess }]
            });

        // Act
        var result = await this._processor.ProcessMessagesAsync(
            messages, "session-123", Activity.UploadText, settings, "user-123", CancellationToken.None);

        // Assert
        Assert.True(result.shouldBlock);
        this._mockPurviewClient.Verify(x => x.ProcessContentAsync(
            It.IsAny<ProcessContentRequest>(), It.IsAny<CancellationToken>()), Times.Once);
    }

    /// <summary>
    /// Verifies an <see cref="AIContent"/> subclass the abstractions do not declare still has its
    /// payload evaluated. Serializing such a type through the polymorphic base type throws, and
    /// substituting its type name would submit no payload at all for classification.
    /// </summary>
    [Fact]
    public async Task ProcessMessagesAsync_WithUnknownContentSubclass_SubmitsPayloadForEvaluationAsync()
    {
        // Arrange
        var messages = new List<ChatMessage>
        {
            new(ChatRole.User, [new UnknownTestContent { Secret = "ssn 123-45-6789" }])
        };
        var settings = CreateValidPurviewSettings();
        var tokenInfo = new TokenInfo { TenantId = "tenant-123", UserId = "user-123", ClientId = "client-123" };

        this._mockPurviewClient.Setup(x => x.GetUserInfoFromTokenAsync(It.IsAny<CancellationToken>(), null))
            .ReturnsAsync(tokenInfo);
        this._mockCacheProvider.Setup(x => x.GetAsync<ProtectionScopesCacheKey, ProtectionScopesResponse>(
            It.IsAny<ProtectionScopesCacheKey>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(CreateApplicableProtectionScopesResponse());

        ProcessContentRequest? capturedRequest = null;
        this._mockPurviewClient.Setup(x => x.ProcessContentAsync(
            It.IsAny<ProcessContentRequest>(), It.IsAny<CancellationToken>()))
            .Callback<ProcessContentRequest, CancellationToken>((request, _) => capturedRequest = request)
            .ReturnsAsync(new ProcessContentResponse());

        // Act
        await this._processor.ProcessMessagesAsync(
            messages, "session-123", Activity.UploadText, settings, "user-123", CancellationToken.None);

        // Assert
        Assert.NotNull(capturedRequest);
        ProcessContentMetadataBase entry = Assert.Single(capturedRequest.ContentToProcess.ContentEntries);
        PurviewTextContent content = Assert.IsType<PurviewTextContent>(entry.Content);

        Assert.Contains("123-45-6789", content.Data, StringComparison.Ordinal);
        Assert.NotEqual(nameof(UnknownTestContent), content.Data);
    }

    #endregion

    #region Helper Methods

    /// <summary>
    /// Stands in for a third-party or future <see cref="AIContent"/> subclass that the abstractions do
    /// not declare a polymorphic discriminator for.
    /// </summary>
    private sealed class UnknownTestContent : AIContent
    {
        public string Secret { get; set; } = string.Empty;
    }

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
            metadata,
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
