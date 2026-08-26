// Copyright (c) Microsoft. All rights reserved.

using Microsoft.AspNetCore.Builder;
using Microsoft.Extensions.DependencyInjection;

namespace Microsoft.Agents.AI.DevUI.UnitTests;

[Collection(nameof(FeatureUsageTestGroup))]
public sealed class FeatureUsageActivationTests
{
    [Fact]
    public void MapDevUI_MarksFeatureUsage()
    {
        // Arrange
        var builder = WebApplication.CreateBuilder();
        builder.Services.AddDevUI();
        using var app = builder.Build();
        FeatureUsageAssert.Reset();

        // Act
        app.MapDevUI();

        // Assert
        FeatureUsageAssert.Marked(64);
    }
}
