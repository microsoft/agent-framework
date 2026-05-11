// Copyright (c) Microsoft. All rights reserved.

namespace Foundry.Hosting.IntegrationTests.Fixtures;

/// <summary>
/// Provisions a hosted agent that runs the test container in <c>IT_SCENARIO=happy-path</c> mode.
/// Used by tests that exercise the basic Responses protocol round trip, multi turn behavior
/// (via <c>previous_response_id</c> and <c>conversation_id</c>), and the <c>stored=false</c> flag.
/// </summary>
public sealed class HappyPathHostedAgentFixture : HostedAgentFixture
{
    protected override string ScenarioName => "happy-path";
}
