// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.AI.Foundry.UnitTests;

public class HostedMcpToolboxAIToolTests
{
    [Fact]
    public void Ctor_NameOnly_BuildsMarkerAddress()
    {
        var tool = new HostedMcpToolboxAITool("my-toolbox");

        Assert.Equal("my-toolbox", tool.ToolboxName);
        Assert.Null(tool.Version);
        Assert.Equal("my-toolbox", tool.ServerName);
        Assert.Equal("foundry-toolbox://my-toolbox", tool.ServerAddress);
        Assert.Equal("mcp", tool.Name);
    }

    [Fact]
    public void Ctor_WithVersion_IncludesVersionQuery()
    {
        var tool = new HostedMcpToolboxAITool("my-toolbox", "v3");

        Assert.Equal("v3", tool.Version);
        Assert.Equal("foundry-toolbox://my-toolbox?version=v3", tool.ServerAddress);
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("   ")]
    public void Ctor_InvalidName_Throws(string? name)
    {
        Assert.ThrowsAny<ArgumentException>(() => new HostedMcpToolboxAITool(name!));
    }

    [Fact]
    public void TryParseToolboxAddress_NameOnly_ReturnsTrue()
    {
        var ok = HostedMcpToolboxAITool.TryParseToolboxAddress(
            "foundry-toolbox://my-toolbox", out var name, out var version);

        Assert.True(ok);
        Assert.Equal("my-toolbox", name);
        Assert.Null(version);
    }

    [Fact]
    public void TryParseToolboxAddress_WithVersion_ExtractsVersion()
    {
        var ok = HostedMcpToolboxAITool.TryParseToolboxAddress(
            "foundry-toolbox://my-toolbox?version=v3", out var name, out var version);

        Assert.True(ok);
        Assert.Equal("my-toolbox", name);
        Assert.Equal("v3", version);
    }

    [Theory]
    [InlineData("https://example.com/mcp")]
    [InlineData("not-a-url")]
    [InlineData("")]
    [InlineData(null)]
    public void TryParseToolboxAddress_NonMarker_ReturnsFalse(string? address)
    {
        var ok = HostedMcpToolboxAITool.TryParseToolboxAddress(address, out var name, out var version);

        Assert.False(ok);
        Assert.Null(name);
        Assert.Null(version);
    }

    [Fact]
    public void TryParseToolboxAddress_RoundTripsFromBuild()
    {
        var address = HostedMcpToolboxAITool.BuildAddress("box", "2025-06-01");

        var ok = HostedMcpToolboxAITool.TryParseToolboxAddress(address, out var name, out var version);

        Assert.True(ok);
        Assert.Equal("box", name);
        Assert.Equal("2025-06-01", version);
    }

    [Fact]
    public void FoundryAITool_CreateHostedMcpToolbox_ReturnsMarker()
    {
        var tool = FoundryAITool.CreateHostedMcpToolbox("my-toolbox", "v1");

        var marker = Assert.IsType<HostedMcpToolboxAITool>(tool);
        Assert.Equal("my-toolbox", marker.ToolboxName);
        Assert.Equal("v1", marker.Version);
    }
}
