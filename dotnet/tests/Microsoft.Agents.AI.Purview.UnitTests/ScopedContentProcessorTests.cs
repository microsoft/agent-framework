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

        this._mockCacheProvider.Setup(x => x.GetAsync<ProtectionScopesCacheKey, ProtectionScopesResponse>(
            It.IsAny<ProtectionScopesCacheKey>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync((ProtectionScopesResponse?)null);

        var psResponse = new ProtectionScopesResponse
        {
            Scopes = new List<PolicyScopeBase>
            {
                new()
                {
                    Activities = ProtectionScopeActivities.UploadText,
                    Locations = new List<PolicyLocation>
                    {
                        new ("microsoft.graph.policyLocationApplication", "app-123")
                    },
                    ExecutionMode = ExecutionMode.EvaluateInline
                }
            }
        };

        this._mockPurviewClient.Setup(x => x.GetProtectionScopesAsync(
            It.IsAny<ProtectionScopesRequest>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(psResponse);

        var pcResponse = new ProcessContentResponse
        {
            PolicyActions = new List<DlpActionInfo>
            {
                new() { Action = DlpAction.BlockAccess }
            }
        };

        this._mockPurviewClient.Setup(x => x.ProcessContentAsync(
            It.IsAny<ProcessContentRequest>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(pcResponse);

        // Act
        var result = await this._processor.ProcessMessagesAsync(
            messages, "thread-123", Activity.UploadText, settings, "user-123", CancellationToken.None);

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

        this._mockCacheProvider.Setup(x => x.GetAsync<ProtectionScopesCacheKey, ProtectionScopesResponse>(
            It.IsAny<ProtectionScopesCacheKey>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync((ProtectionScopesResponse?)null);

        var psResponse = new ProtectionScopesResponse
        {
            Scopes = new List<PolicyScopeBase>
            {
                new()
                {
                    Activities = ProtectionScopeActivities.UploadText,
                    Locations = new List<PolicyLocation>
                    {
                        new ("microsoft.graph.policyLocationApplication", "app-123")
                    },
                    ExecutionMode = ExecutionMode.EvaluateInline
                }
            }
        };

        this._mockPurviewClient.Setup(x => x.GetProtectionScopesAsync(
            It.IsAny<ProtectionScopesRequest>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(psResponse);

        var pcResponse = new ProcessContentResponse
        {
            PolicyActions = new List<DlpActionInfo>
            {
                new() { RestrictionAction = RestrictionAction.Block }
            }
        };

        this._mockPurviewClient.Setup(x => x.ProcessContentAsync(
            It.IsAny<ProcessContentRequest>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(pcResponse);

        // Act
        var result = await this._processor.ProcessMessagesAsync(
            messages, "thread-123", Activity.UploadText, settings, "user-123", CancellationToken.None);

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

        this._mockCacheProvider.Setup(x => x.GetAsync<ProtectionScopesCacheKey, ProtectionScopesResponse>(
            It.IsAny<ProtectionScopesCacheKey>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync((ProtectionScopesResponse?)null);

        var psResponse = new ProtectionScopesResponse
        {
            Scopes = new List<PolicyScopeBase>
            {
                new()
                {
                    Activities = ProtectionScopeActivities.UploadText,
                    Locations = new List<PolicyLocation>
                    {
                        new("microsoft.graph.policyLocationApplication", "app-123")
                    },
                    ExecutionMode = ExecutionMode.EvaluateInline
                }
            }
        };

        this._mockPurviewClient.Setup(x => x.GetProtectionScopesAsync(
            It.IsAny<ProtectionScopesRequest>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(psResponse);

        var pcResponse = new ProcessContentResponse
        {
            PolicyActions = new List<DlpActionInfo>
            {
                new() { Action = DlpAction.NotifyUser }
            }
        };

        this._mockPurviewClient.Setup(x => x.ProcessContentAsync(
            It.IsAny<ProcessContentRequest>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(pcResponse);

        // Act
        var result = await this._processor.ProcessMessagesAsync(
            messages, "thread-123", Activity.UploadText, settings, "user-123", CancellationToken.None);

        // Assert
        Assert.False(result.shouldBlock);
        Assert.Equal("user-123", result.userId);
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
            Scopes = new List<PolicyScopeBase>
            {
                new()
                {
                    Activities = ProtectionScopeActivities.UploadText,
                    Locations = new List<PolicyLocation>
                    {
                        new ("microsoft.graph.policyLocationApplication", "app-123")
                    },
                    ExecutionMode = ExecutionMode.EvaluateInline
                }
            }
        };

        this._mockCacheProvider.Setup(x => x.GetAsync<ProtectionScopesCacheKey, ProtectionScopesResponse>(
            It.IsAny<ProtectionScopesCacheKey>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(cachedPsResponse);

        var pcResponse = new ProcessContentResponse
        {
            PolicyActions = new List<DlpActionInfo>()
        };

        this._mockPurviewClient.Setup(x => x.ProcessContentAsync(
            It.IsAny<ProcessContentRequest>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(pcResponse);

        // Act
        await this._processor.ProcessMessagesAsync(
            messages, "thread-123", Activity.UploadText, settings, "user-123", CancellationToken.None);

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

        this._mockCacheProvider.Setup(x => x.GetAsync<ProtectionScopesCacheKey, ProtectionScopesResponse>(
            It.IsAny<ProtectionScopesCacheKey>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync((ProtectionScopesResponse?)null);

        var psResponse = new ProtectionScopesResponse
        {
            Scopes = new List<PolicyScopeBase>
            {
                new()
                {
                    Activities = ProtectionScopeActivities.UploadText,
                    Locations = new List<PolicyLocation>
                    {
                        new ("microsoft.graph.policyLocationApplication", "app-123")
                    },
                    ExecutionMode = ExecutionMode.EvaluateInline
                }
            }
        };

        this._mockPurviewClient.Setup(x => x.GetProtectionScopesAsync(
            It.IsAny<ProtectionScopesRequest>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(psResponse);

        var pcResponse = new ProcessContentResponse
        {
            ProtectionScopeState = ProtectionScopeState.Modified,
            PolicyActions = new List<DlpActionInfo>()
        };

        this._mockPurviewClient.Setup(x => x.ProcessContentAsync(
            It.IsAny<ProcessContentRequest>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(pcResponse);

        // Act
        await this._processor.ProcessMessagesAsync(
            messages, "thread-123", Activity.UploadText, settings, "user-123", CancellationToken.None);

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

        this._mockCacheProvider.Setup(x => x.GetAsync<ProtectionScopesCacheKey, ProtectionScopesResponse>(
            It.IsAny<ProtectionScopesCacheKey>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync((ProtectionScopesResponse?)null);

        var psResponse = new ProtectionScopesResponse
        {
            Scopes = new List<PolicyScopeBase>
            {
                new()
                {
                    Activities = ProtectionScopeActivities.UploadText,
                    Locations = new List<PolicyLocation>
                    {
                        new ("microsoft.graph.policyLocationApplication", "app-456")
                    }
                }
            }
        };

        this._mockPurviewClient.Setup(x => x.GetProtectionScopesAsync(
            It.IsAny<ProtectionScopesRequest>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(psResponse);

        // Act
        await this._processor.ProcessMessagesAsync(
            messages, "thread-123", Activity.UploadText, settings, "user-123", CancellationToken.None);

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
            this._processor.ProcessMessagesAsync(messages, "thread-123", Activity.UploadText, settings, "user-123", CancellationToken.None));

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
            this._processor.ProcessMessagesAsync(messages, "thread-123", Activity.UploadText, settings, null, CancellationToken.None));

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

        this._mockCacheProvider.Setup(x => x.GetAsync<ProtectionScopesCacheKey, ProtectionScopesResponse>(
            It.IsAny<ProtectionScopesCacheKey>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync((ProtectionScopesResponse?)null);

        var psResponse = new ProtectionScopesResponse { Scopes = new List<PolicyScopeBase>() };
        this._mockPurviewClient.Setup(x => x.GetProtectionScopesAsync(
            It.IsAny<ProtectionScopesRequest>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(psResponse);

        // Act
        var result = await this._processor.ProcessMessagesAsync(
            messages, "thread-123", Activity.UploadText, settings, null, CancellationToken.None);

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

        this._mockCacheProvider.Setup(x => x.GetAsync<ProtectionScopesCacheKey, ProtectionScopesResponse>(
            It.IsAny<ProtectionScopesCacheKey>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync((ProtectionScopesResponse?)null);

        var psResponse = new ProtectionScopesResponse { Scopes = new List<PolicyScopeBase>() };
        this._mockPurviewClient.Setup(x => x.GetProtectionScopesAsync(
            It.IsAny<ProtectionScopesRequest>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(psResponse);

        // Act
        var result = await this._processor.ProcessMessagesAsync(
            messages, "thread-123", Activity.UploadText, settings, null, CancellationToken.None);

        // Assert
        Assert.Equal(userId, result.userId);
    }

    #endregion

    #region Helper Methods

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
