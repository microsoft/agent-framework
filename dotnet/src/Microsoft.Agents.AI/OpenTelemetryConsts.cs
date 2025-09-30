// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI;

/// <summary>Provides constants used by various telemetry services.</summary>
internal static class OpenTelemetryConsts
{
    public const string DefaultSourceName = "Experimental.Microsoft.Agents.AI";

    public static class GenAI
    {
        public const string InvokeAgent = "invoke_agent";

        public static class Agent
        {
            public const string Id = "gen_ai.agent.id";
            public const string Name = "gen_ai.agent.name";
            public const string Description = "gen_ai.agent.description";
        }

        public static class Provider
        {
            public const string Name = "gen_ai.provider.name";
        }
    }
}
