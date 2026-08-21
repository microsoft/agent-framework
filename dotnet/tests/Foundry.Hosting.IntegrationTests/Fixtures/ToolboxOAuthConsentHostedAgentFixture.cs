// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;

namespace Foundry.Hosting.IntegrationTests.Fixtures;

/// <summary>
/// Provisions a hosted agent that runs the test container in <c>IT_SCENARIO=toolbox-oauth-consent</c>
/// mode. The container pre-registers a Foundry toolbox (named by <c>IT_TOOLBOX_NAME</c>) whose tool
/// source is fronted by a per-user OAuth connection. The first request that needs the tool must
/// surface an <c>oauth_consent_request</c> instead of running it.
/// </summary>
/// <remarks>
/// Prerequisite (out of band, per project): a Foundry toolbox named by <see cref="ToolboxName"/> must
/// exist in the target project and reference a tool source that returns <c>CONSENT_REQUIRED</c> for an
/// unconsented user (for example a delegated GitHub or Microsoft Graph connection). Override the
/// toolbox name with the <c>IT_TOOLBOX_NAME</c> environment variable. See the project README.
/// </remarks>
public sealed class ToolboxOAuthConsentHostedAgentFixture : HostedAgentFixture
{
    private const string ToolboxNameEnvironmentVariable = "IT_TOOLBOX_NAME";
    private const string DefaultToolboxName = "auth-paths-oauth-toolbox";

    protected override string ScenarioName => "toolbox-oauth-consent";

    /// <summary>
    /// The Foundry toolbox the container pre-registers. Resolved from <c>IT_TOOLBOX_NAME</c>, falling
    /// back to a default that exists in the reference project.
    /// </summary>
    public string ToolboxName { get; } =
        Environment.GetEnvironmentVariable(ToolboxNameEnvironmentVariable) ?? DefaultToolboxName;

    protected override void ConfigureEnvironment(IDictionary<string, string> environment)
    {
        // Pass the toolbox name into the container so Program.cs wires AddFoundryToolboxes(credential, name).
        // IT_TOOLBOX_NAME is a non-reserved key (FOUNDRY_*/AGENT_* are forbidden by the platform).
        environment[ToolboxNameEnvironmentVariable] = this.ToolboxName;
    }
}
