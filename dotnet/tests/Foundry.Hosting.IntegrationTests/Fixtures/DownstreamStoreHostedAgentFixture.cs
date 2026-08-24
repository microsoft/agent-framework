// Copyright (c) Microsoft. All rights reserved.

namespace Foundry.Hosting.IntegrationTests.Fixtures;

/// <summary>
/// Provisions a hosted agent that runs the test container in <c>IT_SCENARIO=downstream-store</c> mode.
/// Used by <c>HostedDownstreamStoreTests</c>. The container runs an ordinary Foundry
/// <c>ChatClientAgent</c> and reports back which conversation its own run left behind on the service,
/// so the test can check whether a second copy of the turn was kept.
/// </summary>
public sealed class DownstreamStoreHostedAgentFixture : HostedAgentFixture
{
    protected override string ScenarioName => "downstream-store";
}
