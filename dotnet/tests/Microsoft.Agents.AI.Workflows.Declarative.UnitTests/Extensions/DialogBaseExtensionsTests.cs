// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Bot.ObjectModel;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.Extensions;

/// <summary>
/// Tests for <see cref="DialogBaseExtensions"/>.
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
            },
        }.Build();

        // Assert
        Assert.False(dialog.HasSchemaName);

        // Act
        AdaptiveDialog wrappedDialog = dialog.WrapWithBot();

        // Assert
        VerifyWrappedDialog(wrappedDialog);

        // Act & Assert
        VerifyWrappedDialog(wrappedDialog.WrapWithBot());
    }

    private static void VerifyWrappedDialog(AdaptiveDialog wrappedDialog)
    {
        Assert.NotNull(wrappedDialog);
        Assert.NotNull(wrappedDialog.BeginDialog);
        Assert.Equal("test_dialog", wrappedDialog.BeginDialog.Id);
        Assert.True(wrappedDialog.HasSchemaName);
    }
}
