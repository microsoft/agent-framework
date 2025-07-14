// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Provides constants used by agent telemetry services.
/// </summary>
public static class AgentOpenTelemetryConsts
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
    /// Constants for agent operations.
    /// </summary>
    public static class Agent
    {
        /// <summary>
        /// The operation name for agent run operations.
        /// </summary>
        public const string Run = "agent.run";

        /// <summary>
        /// The operation name for agent streaming run operations.
        /// </summary>
        public const string RunStreaming = "agent.run_streaming";

        /// <summary>
        /// Constants for agent operation attributes.
        /// </summary>
        public static class Operation
        {
            /// <summary>
            /// The attribute name for the operation name.
            /// </summary>
            public const string Name = "agent.operation.name";
        }

        /// <summary>
        /// Constants for agent request attributes.
        /// </summary>
        public static class Request
        {
            /// <summary>
            /// The attribute name for the agent request ID.
            /// </summary>
            public const string Id = "agent.request.id";

            /// <summary>
            /// The attribute name for the agent request name.
            /// </summary>
            public const string Name = "agent.request.name";

            /// <summary>
            /// The attribute name for the agent request instructions.
            /// </summary>
            public const string Instructions = "agent.request.instructions";

            /// <summary>
            /// The attribute name for the agent request message count.
            /// </summary>
            public const string MessageCount = "agent.request.message_count";

            /// <summary>
            /// The attribute name for the agent request thread ID.
            /// </summary>
            public const string ThreadId = "agent.request.thread_id";
        }

        /// <summary>
        /// Constants for agent response attributes.
        /// </summary>
        public static class Response
        {
            /// <summary>
            /// The attribute name for the agent response ID.
            /// </summary>
            public const string Id = "agent.response.id";

            /// <summary>
            /// The attribute name for the agent response message count.
            /// </summary>
            public const string MessageCount = "agent.response.message_count";

            /// <summary>
            /// The attribute name for the agent response finish reason.
            /// </summary>
            public const string FinishReason = "agent.response.finish_reason";
        }

        /// <summary>
        /// Constants for agent usage attributes.
        /// </summary>
        public static class Usage
        {
            /// <summary>
            /// The attribute name for input tokens used by the agent.
            /// </summary>
            public const string InputTokens = "agent.usage.input_tokens";

            /// <summary>
            /// The attribute name for output tokens used by the agent.
            /// </summary>
            public const string OutputTokens = "agent.usage.output_tokens";
        }

        /// <summary>
        /// Constants for agent token attributes.
        /// </summary>
        public static class Token
        {
            /// <summary>
            /// The attribute name for the token type.
            /// </summary>
            public const string Type = "agent.token.type";
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
                public const string Name = "agent.client.operation.duration";

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
                public const string Name = "agent.client.token.usage";

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
                public const string Name = "agent.client.request.count";
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
