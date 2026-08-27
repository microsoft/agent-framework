// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Tools.Shell.UnitTests;

[Collection(nameof(FeatureUsageTestGroup))]
public sealed class FeatureUsageActivationTests
{
    [Fact]
    public async Task RunAsync_MarksFeatureUsageAsync()
    {
        // Arrange
        await using var shell = new LocalShellExecutor(new() { Mode = ShellMode.Stateless });
        FeatureUsageAssert.Reset();

        // Act
        _ = await shell.RunAsync("echo feature-usage");

        // Assert
        FeatureUsageAssert.Marked(69);
    }
}
