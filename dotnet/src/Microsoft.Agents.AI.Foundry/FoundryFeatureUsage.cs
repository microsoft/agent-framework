// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Foundry;

internal static class FoundryFeatureUsage
{
    public static void MarkUsed(FeatureIndex feature)
    {
#pragma warning disable MAAI001
        FeatureUsage.MarkUsed((int)feature);
#pragma warning restore MAAI001
    }
}
