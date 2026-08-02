// Copyright (c) Microsoft. All rights reserved.

namespace Foundry.Hosting.IntegrationTests.Fixtures;

/// <summary>
/// Provisions a hosted agent that runs the test container in <c>IT_SCENARIO=session-files</c> mode.
/// The container exposes three local function tools (<c>GetHomeDirectory</c>, <c>ListFiles</c>,
/// <c>ReadFile</c>) that read from the per-session <c>$HOME</c> sandbox volume — mirroring the
/// <c>Hosted-Files</c> sample. Tests use the alpha
/// <see cref="Azure.AI.Projects.Agents.AgentSessionFiles"/> API to upload a file into the session
/// sandbox, then invoke the agent (pinned to the same <c>agent_session_id</c>) and assert that the
/// agent's tools observed the uploaded file.
/// </summary>
public sealed class SessionFilesHostedAgentFixture : HostedAgentFixture
{
    protected override string ScenarioName => "session-files";
}
