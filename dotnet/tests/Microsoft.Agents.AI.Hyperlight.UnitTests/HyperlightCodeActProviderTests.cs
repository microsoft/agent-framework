// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hyperlight.UnitTests;

public sealed class HyperlightCodeActProviderTests
{
    [Fact]
    public void Ctor_NullOptions_UsesDefaults()
    {
        // Act
        using var provider = new HyperlightCodeActProvider();

        // Assert
        Assert.Empty(provider.GetTools());
        Assert.Empty(provider.GetFileMounts());
        Assert.Empty(provider.GetAllowedDomains());
        Assert.Equal([HyperlightCodeActProvider.FixedStateKey], provider.StateKeys);
    }

    [Fact]
    public void StateKeys_IsFixedSingleKey()
    {
        // Arrange
        using var provider = new HyperlightCodeActProvider(new HyperlightCodeActProviderOptions());

        // Act / Assert
        Assert.Equal([HyperlightCodeActProvider.FixedStateKey], provider.StateKeys);
    }

    [Fact]
    public void Tools_Crud_AddReplacesByName()
    {
        // Arrange
        using var provider = new HyperlightCodeActProvider(new HyperlightCodeActProviderOptions());
        var first = AIFunctionFactory.Create(() => "a", name: "t");
        var replacement = AIFunctionFactory.Create(() => "b", name: "t");

        // Act
        provider.AddTools(first);
        provider.AddTools(replacement);

        // Assert
        var tools = provider.GetTools();
        Assert.Single(tools);
        Assert.Same(replacement, tools[0]);
    }

    [Fact]
    public void Tools_RemoveAndClear_Work()
    {
        // Arrange
        using var provider = new HyperlightCodeActProvider(new HyperlightCodeActProviderOptions());
        provider.AddTools(
            AIFunctionFactory.Create(() => "a", name: "a"),
            AIFunctionFactory.Create(() => "b", name: "b"));

        // Act
        provider.RemoveTools("a");

        // Assert
        Assert.Single(provider.GetTools());
        Assert.Equal("b", provider.GetTools()[0].Name);

        // Act
        provider.ClearTools();

        // Assert
        Assert.Empty(provider.GetTools());
    }

    [Fact]
    public void FileMounts_Crud_ReplaceByMountPath()
    {
        // Arrange
        using var provider = new HyperlightCodeActProvider(new HyperlightCodeActProviderOptions());
        var m1 = new FileMount("/host/a", "/input/a");
        var m2 = new FileMount("/host/a-new", "/input/a");
        var m3 = new FileMount("/host/b", "/input/b");

        // Act
        provider.AddFileMounts(m1, m3);
        provider.AddFileMounts(m2);

        // Assert
        var mounts = provider.GetFileMounts().OrderBy(m => m.MountPath).ToArray();
        Assert.Equal(2, mounts.Length);
        Assert.Same(m2, mounts[0]);
        Assert.Same(m3, mounts[1]);

        // Act
        provider.RemoveFileMounts("/input/a");

        // Assert
        Assert.Single(provider.GetFileMounts());

        // Act
        provider.ClearFileMounts();

        // Assert
        Assert.Empty(provider.GetFileMounts());
    }

    [Fact]
    public void AllowedDomains_Crud_ReplaceByTarget()
    {
        // Arrange
        using var provider = new HyperlightCodeActProvider(new HyperlightCodeActProviderOptions());
        var d1 = new AllowedDomain("https://a", new[] { "GET" });
        var d2 = new AllowedDomain("https://a", new[] { "POST" });
        var d3 = new AllowedDomain("https://b");

        // Act
        provider.AddAllowedDomains(d1, d3);
        provider.AddAllowedDomains(d2);

        // Assert
        var domains = provider.GetAllowedDomains().OrderBy(d => d.Target).ToArray();
        Assert.Equal(2, domains.Length);
        Assert.Same(d2, domains[0]);
        Assert.Same(d3, domains[1]);

        // Act
        provider.RemoveAllowedDomains("https://a");

        // Assert
        Assert.Single(provider.GetAllowedDomains());

        // Act
        provider.ClearAllowedDomains();

        // Assert
        Assert.Empty(provider.GetAllowedDomains());
    }

    [Fact]
    public void Ctor_SeedsFromOptions()
    {
        // Arrange
        var tool = AIFunctionFactory.Create(() => "x", name: "x");
        var options = new HyperlightCodeActProviderOptions
        {
            Tools = new[] { tool },
            FileMounts = new[] { new FileMount("/h", "/m") },
            AllowedDomains = new[] { new AllowedDomain("https://a") },
        };

        // Act
        using var provider = new HyperlightCodeActProvider(options);

        // Assert
        Assert.Single(provider.GetTools());
        Assert.Single(provider.GetFileMounts());
        Assert.Single(provider.GetAllowedDomains());
    }

    [Fact]
    public void Dispose_IsIdempotentAndBlocksFurtherAddTools()
    {
        // Arrange
        var provider = new HyperlightCodeActProvider(new HyperlightCodeActProviderOptions());
        var tool = AIFunctionFactory.Create(() => "x", name: "x");

        // Act
        provider.Dispose();
        provider.Dispose();

        // Assert
        Assert.Throws<System.ObjectDisposedException>(() => provider.AddTools(tool));
    }
}
