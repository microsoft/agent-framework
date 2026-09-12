// Copyright (c) Microsoft. All rights reserved.

using System.Globalization;
using System.Numerics;
using System.Reflection;

namespace Microsoft.Agents.AI.Testing;

[CollectionDefinition(nameof(FeatureUsageTestGroup), DisableParallelization = true)]
public sealed class FeatureUsageTestGroup;

internal static class FeatureUsageAssert
{
    public static void Reset()
    {
        MethodInfo? reset = typeof(FeatureUsage).GetMethod(
            "ResetStateForTests",
            BindingFlags.Static | BindingFlags.NonPublic);
        Assert.NotNull(reset);
        reset.Invoke(obj: null, parameters: null);
    }

    public static void Marked(int index)
    {
#pragma warning disable MAAI001 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.
        string userAgent = FeatureUsage.ApplyToUserAgent(string.Empty);
#pragma warning restore MAAI001

        const string Prefix = "(feat=v1.";
        Assert.StartsWith(Prefix, userAgent);
        string maskText = userAgent.Substring(Prefix.Length, userAgent.Length - Prefix.Length - 1);
        BigInteger mask = BigInteger.Parse($"0{maskText}", NumberStyles.AllowHexSpecifier, CultureInfo.InvariantCulture);
        Assert.NotEqual(BigInteger.Zero, mask & (BigInteger.One << index));
    }
}
