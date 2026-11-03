// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;

namespace Foundry.Hosting.IntegrationTests.Fixtures;

/// <summary>
/// Provisions a hosted agent that runs the test container in <c>IT_SCENARIO=mcp-toolbox</c> mode.
/// The container pre-registers a Foundry Toolbox whose PAT-backed GitHub MCP tool can run without
/// user consent, allowing tests to verify the caller-facing MCP execution contract.
/// </summary>
public sealed class McpToolboxHostedAgentFixture : HostedAgentFixture
{
    private const string ToolboxNameEnvironmentVariable = "IT_TOOLBOX_NAME";
    private const string DefaultToolboxName = "auth-paths-pat-toolbox";

    protected override string ScenarioName => "mcp-toolbox";

    /// <summary>
    /// Gets the Foundry Toolbox pre-registered in the hosted test container.
    /// </summary>
    public string ToolboxName { get; } =
        Environment.GetEnvironmentVariable(ToolboxNameEnvironmentVariable) ?? DefaultToolboxName;

    protected override void ConfigureEnvironment(IDictionary<string, string> environment)
    {
        environment[ToolboxNameEnvironmentVariable] = this.ToolboxName;
    }
}
