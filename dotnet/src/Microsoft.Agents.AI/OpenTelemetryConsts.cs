// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI;

/// <summary>Provides constants used by various telemetry services.</summary>
public static class OpenTelemetryConsts
{
    /// <summary>The default <see cref="System.Diagnostics.ActivitySource"/> name used by agent telemetry.</summary>
    public const string DefaultSourceName = "Experimental.Microsoft.Agents.AI";

    /// <summary>OpenTelemetry semantic convention values for generative AI telemetry.</summary>
    public static class GenAI
    {
        /// <summary>The GenAI operation name used for agent invocation spans.</summary>
        public const string InvokeAgent = "invoke_agent";

        /// <summary>GenAI agent attribute names.</summary>
        public static class Agent
        {
            /// <summary>The agent identifier attribute name.</summary>
            public const string Id = "gen_ai.agent.id";

            /// <summary>The agent display name attribute name.</summary>
            public const string Name = "gen_ai.agent.name";

            /// <summary>The agent description attribute name.</summary>
            public const string Description = "gen_ai.agent.description";
        }

        /// <summary>GenAI operation attribute names.</summary>
        public static class Operation
        {
            /// <summary>The operation name attribute name.</summary>
            public const string Name = "gen_ai.operation.name";
        }

        /// <summary>GenAI provider attribute names.</summary>
        public static class Provider
        {
            /// <summary>The provider name attribute name.</summary>
            public const string Name = "gen_ai.provider.name";
        }
    }
}
