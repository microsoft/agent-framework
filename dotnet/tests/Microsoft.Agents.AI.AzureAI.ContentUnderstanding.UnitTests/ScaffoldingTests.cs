// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.AzureAI.ContentUnderstanding.UnitTests;

public sealed class ScaffoldingTests
{
    [Fact]
    public void PackageAssemblyLoads()
    {
        // Confirms the test project's project reference to the package resolves.
        // Replaced with real ContentUnderstandingContextProvider tests in Phase 6.
        Assert.Equal("Microsoft.Agents.AI.AzureAI.ContentUnderstanding", AssemblyMarker.Name);
        Assert.Equal("Microsoft.Agents.AI.AzureAI.ContentUnderstanding", typeof(AssemblyMarker).Assembly.GetName().Name);
    }
}
