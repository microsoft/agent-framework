// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.LocalCodeAct;

internal enum FeatureIndex
{
    LocalCodeAct = 72,
}

internal static class FeatureUsageMarker
{
    public static void MarkUsed()
    {
#pragma warning disable MAAI001 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.
        FeatureUsage.MarkUsed((int)FeatureIndex.LocalCodeAct);
#pragma warning restore MAAI001
    }
}
