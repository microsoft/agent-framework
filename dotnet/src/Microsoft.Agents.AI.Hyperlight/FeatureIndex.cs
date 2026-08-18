// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Hyperlight;

internal enum FeatureIndex
{
    Hyperlight = 70,
}

internal static class FeatureUsageMarker
{
    public static void MarkUsed()
    {
#pragma warning disable MAAI001 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.
        FeatureUsage.MarkUsed((int)FeatureIndex.Hyperlight);
#pragma warning restore MAAI001
    }
}
