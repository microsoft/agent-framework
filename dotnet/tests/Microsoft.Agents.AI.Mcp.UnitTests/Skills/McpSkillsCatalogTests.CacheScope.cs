// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Extensions.Logging.Abstractions;
using ModelContextProtocol.Protocol;

namespace Microsoft.Agents.AI.Skills.Mcp.UnitTests;

public sealed partial class McpSkillsCatalogTests
{
    [Theory]
    [InlineData(null, false, CacheScope.Public)]
    [InlineData(null, true, CacheScope.Public)]
    [InlineData(CacheScope.Public, false, CacheScope.Public)]
    [InlineData(CacheScope.Public, true, CacheScope.Public)]
    [InlineData(CacheScope.Private, true, CacheScope.Private)]
    public void ValidateAndNormalizeCacheScope_AllowedScope_ReturnsNormalizedScope(CacheScope? scope, bool hasIsolationKey, CacheScope expected)
    {
        // Arrange
        var logger = NullLogger.Instance;

        // Act
        CacheScope actual = McpSkillsCatalog.ValidateAndNormalizeCacheScope(scope, hasIsolationKey, logger, "resources/read");

        // Assert
        Assert.Equal(expected, actual);
    }

    [Theory]
    [InlineData("skills/list")]
    [InlineData("skills/get")]
    [InlineData("resources/read")]
    public void ValidateAndNormalizeCacheScope_PrivateWithoutPartitionKey_Throws(string method)
    {
        // Arrange
        var logger = NullLogger.Instance;

        // Act
        var error = Assert.Throws<InvalidOperationException>(() =>
            McpSkillsCatalog.ValidateAndNormalizeCacheScope(CacheScope.Private, false, logger, method));

        // Assert
        Assert.Contains(method, error.Message);
        Assert.Contains(nameof(AgentMcpSkillsSourceOptions.CacheIsolationKeySelector), error.Message);
    }
}
