// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using Moq;

namespace Microsoft.Agents.AI.LocalCodeAct.UnitTests;

[Collection(nameof(FeatureUsageTestGroup))]
public sealed class FeatureUsageActivationTests
{
    [Fact]
    public async Task InvokingAsync_MarksFeatureUsageAsync()
    {
        // Arrange
        using var provider = new LocalCodeActProvider(
            "python",
            new LocalCodeActProviderOptions { ValidationDisabled = true });
        var context = new AIContextProvider.InvokingContext(
            new Mock<AIAgent>().Object,
            session: null,
            new AIContext());
        FeatureUsageAssert.Reset();

        // Act
        _ = await provider.InvokingAsync(context);

        // Assert
        FeatureUsageAssert.Marked(72);
    }
}
