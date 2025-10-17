// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Bot.ObjectModel;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.Extensions;

/// <summary>
/// Tests for DialogBaseExtensions.
/// </summary>
public sealed class DialogBaseExtensionsTests
{
    [Fact]
    public void WrapWithBotCreatesValidBotDefinition()
    {
        // Arrange
        AdaptiveDialog dialog = new AdaptiveDialog.Builder()
        {
            BeginDialog = new OnActivity.Builder()
            {
                Id = "test_dialog",
            }
        }.Build();

        // Act
        AdaptiveDialog wrappedDialog = dialog.WrapWithBot();

        // Assert
        Assert.NotNull(wrappedDialog);
        Assert.NotNull(wrappedDialog.BeginDialog);
        Assert.Equal("test_dialog", wrappedDialog.BeginDialog.Id);
    }
}
