// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.AGUI.A2UI.UnitTests;

/// <summary>
/// Unit tests for <see cref="A2UIConstants"/>.
/// </summary>
/// <remarks>
/// These values are the cross-language A2UI wire contract shared with the TypeScript and
/// Python toolkits; the tests pin them so a refactor cannot silently change the protocol.
/// </remarks>
public sealed class A2UIConstantsTests
{
    [Fact]
    public void A2UIOperationsKey_MatchesCrossLanguageContract()
    {
        // Assert
        Assert.Equal("a2ui_operations", A2UIConstants.A2UIOperationsKey);
    }

    [Fact]
    public void BasicCatalogId_MatchesCrossLanguageContract()
    {
        // Assert
        Assert.Equal("https://a2ui.org/specification/v0_9/basic_catalog.json", A2UIConstants.BasicCatalogId);
    }

    [Fact]
    public void DefaultSurfaceId_MatchesCrossLanguageContract()
    {
        // Assert
        Assert.Equal("dynamic-surface", A2UIConstants.DefaultSurfaceId);
    }

    [Fact]
    public void RecoveryDefaults_MatchCrossLanguageContract()
    {
        // Assert
        Assert.Equal(3, A2UIConstants.MaxA2UIAttempts);
        Assert.Equal("a2ui_recovery", A2UIConstants.A2UIRecoveryActivityType);
    }
}
