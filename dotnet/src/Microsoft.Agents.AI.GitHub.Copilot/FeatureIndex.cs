// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.GitHub.Copilot;

internal enum FeatureIndex
{
    GitHubCopilot = 57,
}

internal static class FeatureUsageMarker
{
    public static void MarkUsed()
    {
#pragma warning disable MAAI001 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.
        FeatureUsage.MarkUsed((int)FeatureIndex.GitHubCopilot);
#pragma warning restore MAAI001
    }
}
