// Copyright (c) Microsoft. All rights reserved.

using System.Linq;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Bot.ObjectModel;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.Extensions;

public sealed class DialogBaseExtensionsTests
{
    [Fact]
    public void WrapWithBotCreatesValidBotDefinition()
    {
        // Arrange
        ObjectModel.SendMessageAction dialog = new ObjectModel.SendMessageAction.Builder
        {
            SchemaName = "test-schema",
            Message = new ObjectModel.AgentMessage.Builder
            {
                Text = "Test message"
            }.Build()
        }.Build();

        // Act
        ObjectModel.SendMessageAction wrappedDialog = dialog.WrapWithBot();

        // Assert
        Assert.NotNull(wrappedDialog);
        Assert.Equal("test-schema", wrappedDialog.SchemaName);
    }

    [Fact]
    public void WrapWithBotUsesDefaultSchemaWhenNotProvided()
    {
        // Arrange
        ObjectModel.SendMessageAction dialog = new ObjectModel.SendMessageAction.Builder
        {
            Message = new ObjectModel.AgentMessage.Builder
            {
                Text = "Test message"
            }.Build()
        }.Build();

        // Act
        ObjectModel.SendMessageAction wrappedDialog = dialog.WrapWithBot();

        // Assert
        Assert.NotNull(wrappedDialog);
    }

    [Fact]
    public void WrapWithBotPreservesDialogProperties()
    {
        // Arrange
        ObjectModel.SendMessageAction dialog = new ObjectModel.SendMessageAction.Builder
        {
            SchemaName = "test-schema",
            Message = new ObjectModel.AgentMessage.Builder
            {
                Text = "Test message"
            }.Build()
        }.Build();

        // Act
        ObjectModel.SendMessageAction wrappedDialog = dialog.WrapWithBot();

        // Assert
        Assert.NotNull(wrappedDialog);
        Assert.Equal("test-schema", wrappedDialog.SchemaName);
        Assert.Equal("Test message", wrappedDialog.Message.Text);
    }

    [Fact]
    public void WrapWithBotCreatesDialogComponentWithCorrectSchema()
    {
        // Arrange
        const string SchemaName = "custom-schema-name";
        ObjectModel.SendMessageAction dialog = new ObjectModel.SendMessageAction.Builder
        {
            SchemaName = SchemaName,
            Message = new ObjectModel.AgentMessage.Builder
            {
                Text = "Test"
            }.Build()
        }.Build();

        // Act
        ObjectModel.SendMessageAction wrappedDialog = dialog.WrapWithBot();

        // Assert
        Assert.NotNull(wrappedDialog);
        Assert.Equal(SchemaName, wrappedDialog.SchemaName);
    }

    [Fact]
    public void WrapWithBotAllowsMultipleWrapping()
    {
        // Arrange
        ObjectModel.SendMessageAction dialog = new ObjectModel.SendMessageAction.Builder
        {
            SchemaName = "test-schema",
            Message = new ObjectModel.AgentMessage.Builder
            {
                Text = "Test message"
            }.Build()
        }.Build();

        // Act
        ObjectModel.SendMessageAction wrappedOnce = dialog.WrapWithBot();
        ObjectModel.SendMessageAction wrappedTwice = wrappedOnce.WrapWithBot();

        // Assert
        Assert.NotNull(wrappedOnce);
        Assert.NotNull(wrappedTwice);
        Assert.Equal("test-schema", wrappedOnce.SchemaName);
        Assert.Equal("test-schema", wrappedTwice.SchemaName);
    }
}
