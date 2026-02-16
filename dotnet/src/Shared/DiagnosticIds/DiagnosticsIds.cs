// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Shared.DiagnosticIds;

/// <summary>
///  Various diagnostic IDs reported by this repo.
/// </summary>
internal static class DiagnosticIds
{
    /// <summary>
    ///  Experiments supported by this repo.
    /// </summary>
    internal static class Experiments
    {
        // This experiment ID is used for all experimental features in the Microsoft Agent Framework.
        internal const string AgentsAIExperiments = "MAAI001";

        // These diagnostic IDs are defined by the MEAI package for its experimental APIs.
        // We use the same IDs so consumers do not need to suppress additional diagnostics
        // when using the experimental MEAI APIs.
        internal const string AIResponseContinuations = AIExperiments;
        internal const string AIMcpServers = AIExperiments;
        internal const string AIFunctionApprovals = AIExperiments;

        // These diagnostic IDs are defined by the OpenAI package for its experimental APIs.
        // We use the same IDs so consumers do not need to suppress additional diagnostics
        // when using the experimental OpenAI APIs.
        internal const string AIOpenAIResponses = "OPENAI001";
        internal const string AIOpenAIAssistants = "OPENAI001";

        private const string AIExperiments = "MEAI001";
    }
}
