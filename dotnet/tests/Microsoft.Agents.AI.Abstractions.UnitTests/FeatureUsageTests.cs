// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ComponentModel;
using System.Diagnostics.CodeAnalysis;
using System.Reflection;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using Moq;

#pragma warning disable MAAI001

namespace Microsoft.Agents.AI.Abstractions.UnitTests;

[Collection(nameof(FeatureUsageTestGroup))]
public sealed partial class FeatureUsageTests : IDisposable
{
    private const string FeatureMaskDisabledEnvironmentVariable = "AGENT_FRAMEWORK_FEATURE_MASK_DISABLED";

    private readonly string? _originalDisabledValue;

    public FeatureUsageTests()
    {
        this._originalDisabledValue = Environment.GetEnvironmentVariable(FeatureMaskDisabledEnvironmentVariable);
        Environment.SetEnvironmentVariable(FeatureMaskDisabledEnvironmentVariable, null);
        FeatureUsage.ResetStateForTests();
    }

    [Theory]
    [InlineData(0, "v1.1")]
    [InlineData(63, "v1.8000000000000000")]
    [InlineData(64, "v1.10000000000000000")]
    [InlineData(127, "v1.80000000000000000000000000000000")]
    public void MarkUsed_BoundaryIndex_ProducesExpectedToken(int index, string expected)
    {
        // Arrange

        // Act
        FeatureUsage.MarkUsed(index);
        string? token = FeatureUsage.GetToken();

        // Assert
        Assert.Equal(expected, token);
    }

    [Theory]
    [InlineData(-1)]
    [InlineData(128)]
    [InlineData(int.MinValue)]
    [InlineData(int.MaxValue)]
    public void MarkUsed_InvalidIndex_ThrowsArgumentOutOfRangeException(int index)
    {
        // Arrange

        // Act
        ArgumentOutOfRangeException exception = Assert.Throws<ArgumentOutOfRangeException>(
            () => FeatureUsage.MarkUsed(index));

        // Assert
        Assert.Equal("index", exception.ParamName);
    }

    [Fact]
    public void MarkUsed_AllBitsConcurrently_AccumulatesEveryBit()
    {
        // Arrange
        int[] indexes = new int[128];
        for (int index = 0; index < indexes.Length; index++)
        {
            indexes[index] = index;
        }

        // Act
        Parallel.ForEach(indexes, FeatureUsage.MarkUsed);
        string? token = FeatureUsage.GetToken();

        // Assert
        Assert.Equal($"v1.{new string('f', 32)}", token);
    }

    [Fact]
    public void MarkUsed_DuplicateIndex_DoesNotChangeToken()
    {
        // Arrange
        FeatureUsage.MarkUsed(42);
        string? originalToken = FeatureUsage.GetToken();

        // Act
        Parallel.For(0, 100, _ => FeatureUsage.MarkUsed(42));
        string? duplicateToken = FeatureUsage.GetToken();

        // Assert
        Assert.Equal("v1.40000000000", duplicateToken);
        Assert.Same(originalToken, duplicateToken);
    }

    [Theory]
    [InlineData("true")]
    [InlineData("TRUE")]
    [InlineData("TrUe")]
    [InlineData("1")]
    public void MarkUsed_Disabled_DoesNotAccumulate(string disabledValue)
    {
        // Arrange
        Environment.SetEnvironmentVariable(FeatureMaskDisabledEnvironmentVariable, disabledValue);
        FeatureUsage.ResetStateForTests();

        // Act
        FeatureUsage.MarkUsed(0);
        FeatureUsage.MarkUsed(127);
        Environment.SetEnvironmentVariable(FeatureMaskDisabledEnvironmentVariable, null);
        FeatureUsage.ReloadDisabledStateForTests();

        // Assert
        Assert.Null(FeatureUsage.GetToken());
    }

    [Fact]
    public void MarkUsed_Disabled_DoesNotValidateIndex()
    {
        // Arrange
        Environment.SetEnvironmentVariable(FeatureMaskDisabledEnvironmentVariable, "true");
        FeatureUsage.ResetStateForTests();

        // Act
        Exception? exception = Record.Exception(() => FeatureUsage.MarkUsed(128));

        // Assert
        Assert.Null(exception);
    }

    [Fact]
    public async Task InMemoryChatHistoryProvider_ActivatesOnlyWhenParticipatingAsync()
    {
        // Arrange
        var provider = new InMemoryChatHistoryProvider();
        var agent = new Mock<AIAgent>().Object;
        var session = new Mock<AgentSession>().Object;
        var context = new ChatHistoryProvider.InvokingContext(agent, session, []);
        Assert.Null(FeatureUsage.GetToken());

        // Act
        _ = await provider.InvokingAsync(context);

        // Assert
        Assert.Equal("v1.2000", FeatureUsage.GetToken());
    }

    [Fact]
    public void Configuration_IsCachedUntilRefreshedForTests()
    {
        // Arrange
        Environment.SetEnvironmentVariable(FeatureMaskDisabledEnvironmentVariable, null);
        FeatureUsage.ResetStateForTests();
        Environment.SetEnvironmentVariable(FeatureMaskDisabledEnvironmentVariable, "true");

        // Act
        FeatureUsage.MarkUsed(7);
        string? token = FeatureUsage.GetToken();

        // Assert
        Assert.Equal("v1.80", token);
    }

    [Fact]
    public void PublicSurface_IsHiddenAndExperimental()
    {
        // Arrange
        Type featureUsageType = typeof(FeatureUsage);
        MethodInfo? markUsedMethod = featureUsageType.GetMethod(nameof(FeatureUsage.MarkUsed));
        MethodInfo? applyMethod = featureUsageType.GetMethod(nameof(FeatureUsage.ApplyToUserAgent));

        // Act
        EditorBrowsableAttribute? editorBrowsable = featureUsageType.GetCustomAttribute<EditorBrowsableAttribute>();
        ExperimentalAttribute? experimental = featureUsageType.GetCustomAttribute<ExperimentalAttribute>();

        // Assert
        Assert.NotNull(markUsedMethod);
        Assert.NotNull(applyMethod);
        Assert.Equal(EditorBrowsableState.Never, editorBrowsable?.State);
        Assert.Equal("MAAI001", experimental?.DiagnosticId);
    }

    [Fact]
    public void GetToken_UsesLowercaseVersionedHexFormat()
    {
        // Arrange
        FeatureUsage.MarkUsed(1);
        FeatureUsage.MarkUsed(63);
        FeatureUsage.MarkUsed(64);
        FeatureUsage.MarkUsed(127);

        // Act
        string? token = FeatureUsage.GetToken();

        // Assert
        Assert.NotNull(token);
        Assert.Matches(new Regex("^v1\\.[0-9a-f]{1,32}$", RegexOptions.CultureInvariant), token);
    }

    [Fact]
    public void GetToken_UnchangedMask_ReturnsCachedTokenInstance()
    {
        // Arrange
        FeatureUsage.MarkUsed(12);
        string? originalToken = FeatureUsage.GetToken();

        // Act
        string? cachedToken = FeatureUsage.GetToken();
        FeatureUsage.MarkUsed(12);
        string? deduplicatedToken = FeatureUsage.GetToken();
        FeatureUsage.MarkUsed(13);
        string? changedToken = FeatureUsage.GetToken();

        // Assert
        Assert.Same(originalToken, cachedToken);
        Assert.Same(originalToken, deduplicatedToken);
        Assert.NotSame(originalToken, changedToken);
        Assert.Equal("v1.3000", changedToken);
        Assert.Equal("v1.1000", originalToken);
    }

    [Fact]
    public void GetToken_BitsInBothLanes_PadsLowLane()
    {
        // Arrange
        FeatureUsage.MarkUsed(1);
        FeatureUsage.MarkUsed(65);

        // Act
        string? token = FeatureUsage.GetToken();

        // Assert
        Assert.Equal("v1.20000000000000002", token);
    }

    [Fact]
    public void GetToken_EmptyMask_ReturnsNull()
    {
        // Arrange

        // Act
        string? token = FeatureUsage.GetToken();

        // Assert
        Assert.Null(token);
    }

    [Theory]
    [InlineData("", "")]
    [InlineData("app/1.0", "app/1.0")]
    [InlineData("  app/1.0  ", "  app/1.0  ")]
    [InlineData("app/1.0 (custom=value)", "app/1.0 (custom=value)")]
    [InlineData("app/1.0 (feat=v1.)", "app/1.0 (feat=v1.)")]
    [InlineData("app/1.0 (feat=vx.1)", "app/1.0 (feat=vx.1)")]
    [InlineData("app/1.0 (feat=v1.1g)", "app/1.0 (feat=v1.1g)")]
    [InlineData("app/1.0(feat=v1.1)", "app/1.0(feat=v1.1)")]
    [InlineData("app/1.0 (feat=v1.1)suffix", "app/1.0 (feat=v1.1)suffix")]
    public void ApplyToUserAgent_NoToken_PreservesHeaderWithoutValidFeatureCommentByteForByte(
        string userAgent,
        string expected)
    {
        // Arrange

        // Act
        string actual = FeatureUsage.ApplyToUserAgent(userAgent);

        // Assert
        Assert.Equal(expected, actual);
    }

    [Theory]
    [InlineData("app/1.0 (feat=v1.1)", "app/1.0")]
    [InlineData("(feat=v1.1)", "")]
    [InlineData("(feat=v1.1) app/1.0", "app/1.0")]
    [InlineData("app/1.0 (feat=v2.AB)", "app/1.0")]
    [InlineData("app/1.0 (feat=v1.1) (feat=v2.2)", "app/1.0")]
    [InlineData("app/1.0  (feat=v1.1)", "app/1.0 ")]
    public void ApplyToUserAgent_Excluded_StripsOnlyValidFeatureComments(string userAgent, string expected)
    {
        // Arrange

        // Act
        string actual = FeatureUsage.ApplyToUserAgent(userAgent, includeFeatureToken: false);

        // Assert
        Assert.Equal(expected, actual);
    }

    [Fact]
    public void ApplyToUserAgent_RefreshesStaleComment_PreservesUnrelatedBytes_AndIsIdempotent()
    {
        // Arrange
        const string Original = "vendor/2.0 (custom=a) app/1.0 (feat=v1.1)";
        FeatureUsage.MarkUsed(5);

        // Act
        string refreshed = FeatureUsage.ApplyToUserAgent(Original);
        string repeated = FeatureUsage.ApplyToUserAgent(refreshed);

        // Assert
        Assert.Equal("vendor/2.0 (custom=a) app/1.0 (feat=v1.20)", refreshed);
        Assert.Equal(refreshed, repeated);
    }

    [Fact]
    public void ApplyToUserAgent_NullUserAgent_ThrowsArgumentNullException()
    {
        // Arrange / Act
        ArgumentNullException exception = Assert.Throws<ArgumentNullException>(
            () => FeatureUsage.ApplyToUserAgent(null!));

        // Assert
        Assert.Equal("userAgent", exception.ParamName);
    }

    public void Dispose()
    {
        Environment.SetEnvironmentVariable(FeatureMaskDisabledEnvironmentVariable, this._originalDisabledValue);
        FeatureUsage.ResetStateForTests();
    }

    [CollectionDefinition(nameof(FeatureUsageTestGroup), DisableParallelization = true)]
    public sealed class FeatureUsageTestGroup;
}
