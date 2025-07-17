// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Provides constants used by agent telemetry services following OpenTelemetry semantic conventions.
/// <see href="https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-agent-spans/"/>
/// </summary>
internal static class AgentOpenTelemetryConsts
{
    /// <summary>
    /// The default source name for agent telemetry.
    /// </summary>
    public const string DefaultSourceName = "Microsoft.Extensions.AI.Agents";

    /// <summary>
    /// The unit for seconds measurements.
    /// </summary>
    public const string SecondsUnit = "s";

    /// <summary>
    /// The unit for token measurements.
    /// </summary>
    public const string TokensUnit = "token";

    /// <summary>
    /// Constants for generative AI telemetry, following OpenTelemetry semantic conventions.
    /// </summary>
    public static class GenAI
    {
        /// <summary>
        /// The attribute name for the GenAI operation name (following gen_ai.operation.name convention).
        /// </summary>
        public const string OperationName = "gen_ai.operation.name";

        /// <summary>
        /// The attribute name for the GenAI system (following gen_ai.system convention).
        /// </summary>
        public const string System = "gen_ai.system";

        /// <summary>
        /// The attribute name for the GenAI conversation ID (following gen_ai.conversation.id convention).
        /// </summary>
        public const string ConversationId = "gen_ai.conversation.id";

        /// <summary>
        /// Constants for official GenAI operation names as defined in OpenTelemetry semantic conventions.
        /// </summary>
        public static class Operations
        {
            /// <summary>
            /// Invoke GenAI agent operation.
            /// </summary>
            public const string InvokeAgent = "invoke_agent";
        }

        /// <summary>
        /// Constants for GenAI system values as defined in OpenTelemetry semantic conventions.
        /// </summary>
        public static class Systems
        {
            /// <summary>
            /// Microsoft Extensions AI system identifier.
            /// </summary>
            public const string MicrosoftExtensionsAI = "microsoft.extensions.ai";
        }

        /// <summary>
        /// Constants for agent-related telemetry attributes and operations.
        /// </summary>
        public static class Agent
        {
            /// <summary>
            /// The attribute name for the agent ID (following gen_ai.agent.id convention).
            /// </summary>
            public const string Id = "gen_ai.agent.id";

            /// <summary>
            /// The attribute name for the agent name (following gen_ai.agent.name convention).
            /// </summary>
            public const string Name = "gen_ai.agent.name";

            /// <summary>
            /// The attribute name for the agent description (following gen_ai.agent.description convention).
            /// </summary>
            public const string Description = "gen_ai.agent.description";

            /// <summary>
            /// Constants for agent request attributes.
            /// </summary>
            public static class Request
            {
                /// <summary>
                /// The attribute name for the agent request instructions.
                /// </summary>
                public const string Instructions = "gen_ai.agent.request.instructions";

                /// <summary>
                /// The attribute name for the agent request message count.
                /// </summary>
                public const string MessageCount = "gen_ai.agent.request.message_count";
            }

            /// <summary>
            /// Constants for agent response attributes.
            /// </summary>
            public static class Response
            {
                /// <summary>
                /// The attribute name for the agent response ID.
                /// </summary>
                public const string Id = "gen_ai.agent.response.id";

                /// <summary>
                /// The attribute name for the agent response message count.
                /// </summary>
                public const string MessageCount = "gen_ai.agent.response.message_count";
            }

            /// <summary>
            /// Constants for agent usage attributes.
            /// </summary>
            public static class Usage
            {
                /// <summary>
                /// The attribute name for input tokens used by the agent.
                /// </summary>
                public const string InputTokens = "gen_ai.agent.usage.input_tokens";

                /// <summary>
                /// The attribute name for output tokens used by the agent.
                /// </summary>
                public const string OutputTokens = "gen_ai.agent.usage.output_tokens";
            }

            /// <summary>
            /// Constants for agent token attributes.
            /// </summary>
            public static class Token
            {
                /// <summary>
                /// The attribute name for the token type.
                /// </summary>
                public const string Type = "gen_ai.agent.token.type";
            }

            /// <summary>
            /// Constants for agent client metrics.
            /// </summary>
            public static class Client
            {
                /// <summary>
                /// Constants for operation duration metrics.
                /// </summary>
                public static class OperationDuration
                {
                    /// <summary>
                    /// The description for the operation duration metric.
                    /// </summary>
                    public const string Description = "Measures the duration of an agent operation";

                    /// <summary>
                    /// The name for the operation duration metric.
                    /// </summary>
                    public const string Name = "gen_ai.agent.client.operation.duration";

                    /// <summary>
                    /// The explicit bucket boundaries for the operation duration histogram.
                    /// </summary>
                    public static readonly double[] ExplicitBucketBoundaries = [0.01, 0.02, 0.04, 0.08, 0.16, 0.32, 0.64, 1.28, 2.56, 5.12, 10.24, 20.48, 40.96, 81.92];
                }

                /// <summary>
                /// Constants for token usage metrics.
                /// </summary>
                public static class TokenUsage
                {
                    /// <summary>
                    /// The description for the token usage metric.
                    /// </summary>
                    public const string Description = "Measures number of input and output tokens used by agent";

                    /// <summary>
                    /// The name for the token usage metric.
                    /// </summary>
                    public const string Name = "gen_ai.agent.client.token.usage";

                    /// <summary>
                    /// The explicit bucket boundaries for the token usage histogram.
                    /// </summary>
                    public static readonly int[] ExplicitBucketBoundaries = [1, 4, 16, 64, 256, 1_024, 4_096, 16_384, 65_536, 262_144, 1_048_576, 4_194_304, 16_777_216, 67_108_864];
                }

                /// <summary>
                /// Constants for request count metrics.
                /// </summary>
                public static class RequestCount
                {
                    /// <summary>
                    /// The description for the request count metric.
                    /// </summary>
                    public const string Description = "Measures the number of agent requests";

                    /// <summary>
                    /// The name for the request count metric.
                    /// </summary>
                    public const string Name = "gen_ai.agent.client.request.count";
                }
            }
        }
    }

    /// <summary>
    /// Constants for error attributes.
    /// </summary>
    public static class ErrorInfo
    {
        /// <summary>
        /// The attribute name for the error type.
        /// </summary>
        public const string Type = "error.type";
    }

    /// <summary>
    /// Constants for event attributes.
    /// </summary>
    public static class EventInfo
    {
        /// <summary>
        /// The attribute name for the event name.
        /// </summary>
        public const string Name = "event.name";
    }
}
