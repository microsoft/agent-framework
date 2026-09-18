// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Foundry.Hosting.UnitTests;

/// <summary>
/// Tests for <see cref="HostedConversationKey"/>, which derives the stable per-conversation key used
/// to map a hosted request to a persisted MAF session.
/// </summary>
public class HostedConversationKeyTests
{
    // 18-char partition + 32-char entropy = 50-char body (current format).
    private const string PartitionA = "aaaaaaaaaaaaaaaa00";
    private static readonly string s_responseA = "caresp_" + PartitionA + new string('1', 32);
    private static readonly string s_responseA2 = "caresp_" + PartitionA + new string('2', 32);

    [Fact]
    public void PartitionOf_NewFormat_ReturnsFirst18()
        => Assert.Equal(PartitionA, HostedConversationKey.PartitionOf(s_responseA));

    [Fact]
    public void PartitionOf_SamePartition_AcrossChain_Matches()
        => Assert.Equal(HostedConversationKey.PartitionOf(s_responseA), HostedConversationKey.PartitionOf(s_responseA2));

    [Fact]
    public void PartitionOf_LegacyFormat_ReturnsLast16()
    {
        var legacy = "caresp_" + new string('x', 32) + "abcdefabcdef1234"; // 48-char body
        Assert.Equal("abcdefabcdef1234", HostedConversationKey.PartitionOf(legacy));
    }

    [Fact]
    public void PartitionOf_Raw_WhenNoKnownLength() => Assert.Equal("conv-123", HostedConversationKey.PartitionOf("conv-123"));

    [Fact]
    public void PartitionOf_NullOrWhitespace_ReturnsNull()
    {
        Assert.Null(HostedConversationKey.PartitionOf(null));
        Assert.Null(HostedConversationKey.PartitionOf(" "));
    }

    [Fact]
    public void Resolve_PrefersConversation_ThenPrev_ThenResponse()
    {
        Assert.Equal("conv", HostedConversationKey.Resolve("conv", s_responseA, s_responseA2));
        Assert.Equal(PartitionA, HostedConversationKey.Resolve(null, s_responseA, "caresp_" + new string('9', 50)));
        Assert.Equal(PartitionA, HostedConversationKey.Resolve(null, null, s_responseA));
        Assert.Null(HostedConversationKey.Resolve(null, null, null));
    }
}
