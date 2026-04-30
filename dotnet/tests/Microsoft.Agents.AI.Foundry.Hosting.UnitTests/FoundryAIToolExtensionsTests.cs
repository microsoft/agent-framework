// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Agents.AI.Foundry.Hosting;

namespace Microsoft.Agents.AI.Foundry.UnitTests.Hosting;

public class FoundryAIToolExtensionsTests
{
    [Fact]
    public void CreateHostedMcpToolbox_FromToolboxRecord_UsesNameAndDefaultVersion()
    {
        var record = Azure.AI.Projects.Agents.ProjectsAgentsModelFactory.ToolboxRecord(
            id: "tbx-123",
            name: "calendar-tools",
            defaultVersion: "v2");

        var tool = FoundryAIToolExtensions.CreateHostedMcpToolbox(record);

        var marker = Assert.IsType<HostedMcpToolboxAITool>(tool);
        Assert.Equal("calendar-tools", marker.ToolboxName);
        Assert.Equal("v2", marker.Version);
        Assert.Equal("foundry-toolbox://calendar-tools?version=v2", marker.ServerAddress);
    }

    [Fact]
    public void CreateHostedMcpToolbox_FromToolboxRecord_NullDefaultVersionOmitsQuery()
    {
        var record = Azure.AI.Projects.Agents.ProjectsAgentsModelFactory.ToolboxRecord(
            id: "tbx-abc",
            name: "finance-tools",
            defaultVersion: null);

        var tool = FoundryAIToolExtensions.CreateHostedMcpToolbox(record);

        var marker = Assert.IsType<HostedMcpToolboxAITool>(tool);
        Assert.Equal("finance-tools", marker.ToolboxName);
        Assert.Null(marker.Version);
        Assert.Equal("foundry-toolbox://finance-tools", marker.ServerAddress);
    }

    [Fact]
    public void CreateHostedMcpToolbox_FromToolboxRecord_Null_Throws()
    {
        Assert.Throws<ArgumentNullException>(
            () => FoundryAIToolExtensions.CreateHostedMcpToolbox((Azure.AI.Projects.Agents.ToolboxRecord)null!));
    }

    [Fact]
    public void CreateHostedMcpToolbox_FromToolboxVersion_UsesNameAndVersion()
    {
        var version = Azure.AI.Projects.Agents.ProjectsAgentsModelFactory.ToolboxVersion(
            metadata: null,
            id: "ver-1",
            name: "hr-tools",
            version: "2025-09-01",
            description: "HR toolbox",
            createdAt: DateTimeOffset.UtcNow,
            tools: null,
            policies: null);

        var tool = FoundryAIToolExtensions.CreateHostedMcpToolbox(version);

        var marker = Assert.IsType<HostedMcpToolboxAITool>(tool);
        Assert.Equal("hr-tools", marker.ToolboxName);
        Assert.Equal("2025-09-01", marker.Version);
        Assert.Equal("foundry-toolbox://hr-tools?version=2025-09-01", marker.ServerAddress);
    }

    [Fact]
    public void CreateHostedMcpToolbox_FromToolboxVersion_Null_Throws()
    {
        Assert.Throws<ArgumentNullException>(
            () => FoundryAIToolExtensions.CreateHostedMcpToolbox((Azure.AI.Projects.Agents.ToolboxVersion)null!));
    }
}
