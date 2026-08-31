// Copyright (c) Microsoft. All rights reserved.

namespace Foundry.Hosting.IntegrationTests.Fixtures;

/// <summary>
/// Provisions a hosted agent that runs the test container in <c>IT_SCENARIO=store-config</c> mode.
/// Used by <c>HostedResponsesStoreConfigTests</c> to exercise store/session semantics: <c>store=true</c>
/// vs <c>store=false</c>, <c>previous_response_id</c> and <c>conversation_id</c> forks, and multi-turn
/// recall. The container agent is a neutral assistant with no marker instruction so it never
/// contaminates the content assertions.
/// </summary>
public sealed class HostedResponsesStoreConfigFixture : HostedAgentFixture
{
    protected override string ScenarioName => "store-config";
}
