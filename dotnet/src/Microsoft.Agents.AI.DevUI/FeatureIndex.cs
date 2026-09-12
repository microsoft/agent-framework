// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.DevUI;

internal enum FeatureIndex
{
    DevUI = 64,
}

internal static class FeatureUsageMarker
{
    public static void MarkUsed()
    {
#pragma warning disable MAAI001 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.
        FeatureUsage.MarkUsed((int)FeatureIndex.DevUI);
#pragma warning restore MAAI001
    }
}
