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

        // This experiment ID is used for Agent Framework extensions over Anthropic beta services.
        internal const string AIAnthropicBetaServices = "MAAIANTHROPIC001";

        // These diagnostic IDs are defined by the MEAI package for its experimental APIs.
        // We use the same IDs so consumers do not need to suppress additional diagnostics
        // when using the experimental MEAI APIs.
        internal const string AIResponseContinuations = MEAIExperiments;
        internal const string AIMcpServers = MEAIExperiments;
        internal const string AIFunctionApprovals = MEAIExperiments;
        internal const string AIOpenAIRequestPolicies = MEAIExperiments;

        // These diagnostic IDs are defined by the OpenAI package for its experimental APIs.
        // We use the same IDs so consumers do not need to suppress additional diagnostics
        // when using the experimental OpenAI APIs.
        internal const string AIOpenAIResponses = "OPENAI001";

        // The OpenAI package used OPENAICUA001 for its computer use APIs until 2.13.0, which folded
        // them into OPENAI001 (openai/openai-dotnet#1245). The ID now only gates the computer tool
        // factories in this repo; it is kept so existing suppressions of the preview factory keep working.
        internal const string AIOpenAIComputerUse = "OPENAICUA001";

        private const string MEAIExperiments = "MEAI001";
    }
}
