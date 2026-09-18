// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI;

internal static class TestAgentSkillsSourceContextFactory
{
    public static AgentSkillsSourceContext Create(AIAgent? agent = null)
        => new(agent ?? new TestAIAgent(), session: null);
}
