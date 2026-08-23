// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;

namespace Foundry.Hosting.IntegrationTests.Fixtures;

/// <summary>
/// Provisions a hosted agent that runs the test container in
/// <c>IT_SCENARIO=resilient-workflow</c> mode.
/// </summary>
public sealed class ResilientWorkflowHostedAgentFixture : HostedAgentFixture
{
    protected override string ScenarioName => "resilient-workflow";

    protected override TimeSpan ProvisioningTimeout => TimeSpan.FromMinutes(8);

    protected override void ConfigureEnvironment(IDictionary<string, string> environment)
    {
        environment["IT_LONG_RUNNING_DELAY_SECONDS"] = "20";
        environment["IT_COUNTDOWN_DELAY_MILLISECONDS"] = "250";
        environment["IT_COUNTDOWN_CRASH_DELAY_SECONDS"] = "5";
    }
}
