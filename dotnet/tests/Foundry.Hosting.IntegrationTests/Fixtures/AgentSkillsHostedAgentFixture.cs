// Copyright (c) Microsoft. All rights reserved.

namespace Foundry.Hosting.IntegrationTests.Fixtures;

/// <summary>
/// Provisions a hosted agent that runs the test container in <c>IT_SCENARIO=agent-skills</c> mode.
/// The container creates two Contoso Outdoors skills (support-style, escalation-policy) on disk
/// and wires them into <see cref="Microsoft.Agents.AI.AgentSkillsProvider"/> so the model can
/// discover and load skills via the progressive disclosure pattern.
/// </summary>
public sealed class AgentSkillsHostedAgentFixture : HostedAgentFixture
{
    protected override string ScenarioName => "agent-skills";
}
