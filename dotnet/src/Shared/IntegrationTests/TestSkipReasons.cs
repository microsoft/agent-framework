// Copyright (c) Microsoft. All rights reserved.

namespace Shared.IntegrationTests;

/// <summary>
/// Skip reasons used to temporarily disable integration tests whose backing service is unavailable in CI.
/// </summary>
internal static class TestSkipReasons
{
    /// <summary>
    /// Skips every OpenAI integration test while the CI OpenAI API key is rejected.
    /// Set to <see langword="null"/> to run the OpenAI integration tests again.
    /// </summary>
    public const string? OpenAIIntegrationTests = "OpenAI integration tests are temporarily disabled: the CI OpenAI API key is invalid.";
}
