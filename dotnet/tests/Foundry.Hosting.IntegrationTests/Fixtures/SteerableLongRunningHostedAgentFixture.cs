// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;

namespace Foundry.Hosting.IntegrationTests.Fixtures;

/// <summary>
/// Provisions a hosted agent that runs the test container in
/// <c>IT_SCENARIO=steerable-long-running</c> mode.
/// </summary>
public sealed class SteerableLongRunningHostedAgentFixture : HostedAgentFixture
{
    protected override string ScenarioName => "steerable-long-running";

    protected override TimeSpan ProvisioningTimeout => TimeSpan.FromMinutes(8);

    protected override void ConfigureEnvironment(
        IDictionary<string, string> environment)
    {
        environment["IT_STEERING_LONG_RUNNING_DELAY_SECONDS"] = "30";
    }
}
