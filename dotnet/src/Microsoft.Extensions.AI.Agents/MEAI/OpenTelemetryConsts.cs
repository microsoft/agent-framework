// Copyright (c) Microsoft. All rights reserved.

// WARNING:
// This class has been temporarily copied here from MEAI, to allow prototyping
// functionality that will be moved to MEAI in the future.
// This file is not intended to be modified.

using System.Diagnostics.CodeAnalysis;

namespace Microsoft.Extensions.AI;

#pragma warning disable CA1716 // Identifiers should not match keywords
#pragma warning disable S4041 // Type names should not match namespaces

/// <summary>Provides constants used by various telemetry services.</summary>
[ExcludeFromCodeCoverage]
internal static class OpenTelemetryConsts
{
    public const string DefaultSourceName = "Experimental.Microsoft.Extensions.AI";

    public const string SecondsUnit = "s";
    public const string TokensUnit = "token";

    public static class Event
    {
        public const string Name = "event.name";
    }

    public static class Error
    {
        public const string Type = "error.type";
    }

    public static class GenAI
    {
        public const string Choice = "gen_ai.choice";
        public const string SystemName = "gen_ai.system";

        public const string Chat = "chat";
        public const string Embeddings = "embeddings";
        public const string ExecuteTool = "execute_tool";

        public static class Assistant
        {
            public const string Message = "gen_ai.assistant.message";
        }

        public static class Client
        {
            public static class OperationDuration
            {
                public const string Description = "Measures the duration of a GenAI operation";
                public const string Name = "gen_ai.client.operation.duration";
                public static readonly double[] ExplicitBucketBoundaries = [0.01, 0.02, 0.04, 0.08, 0.16, 0.32, 0.64, 1.28, 2.56, 5.12, 10.24, 20.48, 40.96, 81.92];
            }

            public static class TokenUsage
            {
                public const string Description = "Measures number of input and output tokens used";
                public const string Name = "gen_ai.client.token.usage";
                public static readonly int[] ExplicitBucketBoundaries = [1, 4, 16, 64, 256, 1_024, 4_096, 16_384, 65_536, 262_144, 1_048_576, 4_194_304, 16_777_216, 67_108_864];
            }
        }

        public static class Conversation
        {
            public const string Id = "gen_ai.conversation.id";
        }

        public static class Operation
        {
            public const string Name = "gen_ai.operation.name";
        }

        public static class Output
        {
            public const string Type = "gen_ai.output.type";
        }

        public static class Request
        {
            public const string EmbeddingDimensions = "gen_ai.request.embedding.dimensions";
            public const string FrequencyPenalty = "gen_ai.request.frequency_penalty";
            public const string Model = "gen_ai.request.model";
            public const string MaxTokens = "gen_ai.request.max_tokens";
            public const string PresencePenalty = "gen_ai.request.presence_penalty";
            public const string Seed = "gen_ai.request.seed";
            public const string StopSequences = "gen_ai.request.stop_sequences";
            public const string Temperature = "gen_ai.request.temperature";
            public const string TopK = "gen_ai.request.top_k";
            public const string TopP = "gen_ai.request.top_p";

            public static string PerProvider(string providerName, string parameterName) => $"gen_ai.{providerName}.request.{parameterName}";
        }

        public static class Response
        {
            public const string FinishReasons = "gen_ai.response.finish_reasons";
            public const string Id = "gen_ai.response.id";
            public const string Model = "gen_ai.response.model";

            public static string PerProvider(string providerName, string parameterName) => $"gen_ai.{providerName}.response.{parameterName}";
        }

        public static class System
        {
            public const string Message = "gen_ai.system.message";
        }

        public static class Token
        {
            public const string Type = "gen_ai.token.type";
        }

        public static class Tool
        {
            public const string Name = "gen_ai.tool.name";
            public const string Description = "gen_ai.tool.description";
            public const string Message = "gen_ai.tool.message";

            public static class Call
            {
                public const string Id = "gen_ai.tool.call.id";
            }
        }

        public static class Usage
        {
            public const string InputTokens = "gen_ai.usage.input_tokens";
            public const string OutputTokens = "gen_ai.usage.output_tokens";
        }

        public static class User
        {
            public const string Message = "gen_ai.user.message";
        }
    }

    public static class Server
    {
        public const string Address = "server.address";
        public const string Port = "server.port";
    }
}
