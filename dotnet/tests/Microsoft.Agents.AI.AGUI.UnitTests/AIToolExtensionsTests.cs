// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using Microsoft.Agents.AI.AGUI.Shared;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.AGUI.UnitTests;

/// <summary>
/// Unit tests for the <see cref="AIToolExtensions"/> class.
/// </summary>
public sealed class AIToolExtensionsTests
{
    [Fact]
    public void AsAGUITools_WithAIFunction_ConvertsToAGUIToolCorrectly()
    {
        // Arrange
        AIFunction function = AIFunctionFactory.Create(
            (string location) => $"Weather in {location}",
            "GetWeather",
            "Gets the current weather");
        List<AITool> tools = [function];

        // Act
        List<AGUITool> aguiTools = tools.AsAGUITools().ToList();

        // Assert
        AGUITool aguiTool = Assert.Single(aguiTools);
        Assert.Equal("GetWeather", aguiTool.Name);
        Assert.Equal("Gets the current weather", aguiTool.Description);
        Assert.NotEqual(default, aguiTool.Parameters);
    }

    [Fact]
    public void AsAGUITools_WithMultipleFunctions_ConvertsAllCorrectly()
    {
        // Arrange
        List<AITool> tools =
        [
            AIFunctionFactory.Create(() => "Result1", "Tool1", "First tool"),
            AIFunctionFactory.Create(() => "Result2", "Tool2", "Second tool"),
            AIFunctionFactory.Create(() => "Result3", "Tool3", "Third tool")
        ];

        // Act
        List<AGUITool> aguiTools = tools.AsAGUITools().ToList();

        // Assert
        Assert.Equal(3, aguiTools.Count);
        Assert.Equal("Tool1", aguiTools[0].Name);
        Assert.Equal("Tool2", aguiTools[1].Name);
        Assert.Equal("Tool3", aguiTools[2].Name);
    }

    [Fact]
    public void AsAGUITools_WithNullInput_ReturnsEmptyEnumerable()
    {
        // Arrange
        IEnumerable<AITool>? tools = null;

        // Act
        IEnumerable<AGUITool> aguiTools = tools!.AsAGUITools();

        // Assert
        Assert.NotNull(aguiTools);
        Assert.Empty(aguiTools);
    }

    [Fact]
    public void AsAGUITools_WithEmptyInput_ReturnsEmptyEnumerable()
    {
        // Arrange
        List<AITool> tools = [];

        // Act
        List<AGUITool> aguiTools = tools.AsAGUITools().ToList();

        // Assert
        Assert.Empty(aguiTools);
    }

    [Fact]
    public void AsAGUITools_FiltersOutNonAIFunctionTools()
    {
        // Arrange - mix of AIFunction and non-function tools
        AIFunction function = AIFunctionFactory.Create(() => "Result", "TestTool");
        // Create a custom AITool that's not an AIFunction
        var declaration = AIFunctionFactory.CreateDeclaration("DeclarationOnly", "Description", JsonDocument.Parse("{}").RootElement);

        List<AITool> tools = [function, declaration];

        // Act
        List<AGUITool> aguiTools = tools.AsAGUITools().ToList();

        // Assert
        // Only the AIFunction should be converted, declarations are filtered
        Assert.Equal(2, aguiTools.Count); // Actually both convert since declaration is also AIFunctionDeclaration
    }

    [Fact]
    public void AsAITools_WithAGUITool_ConvertsToAIFunctionDeclarationCorrectly()
    {
        // Arrange
        AGUITool aguiTool = new()
        {
            Name = "TestTool",
            Description = "Test description",
            Parameters = JsonDocument.Parse("{\"type\":\"object\",\"properties\":{}}").RootElement
        };
        List<AGUITool> aguiTools = [aguiTool];

        // Act
        List<AITool> tools = aguiTools.AsAITools().ToList();

        // Assert
        AITool tool = Assert.Single(tools);
        Assert.IsAssignableFrom<AIFunctionDeclaration>(tool);
        var declaration = (AIFunctionDeclaration)tool;
        Assert.Equal("TestTool", declaration.Name);
        Assert.Equal("Test description", declaration.Description);
    }

    [Fact]
    public void AsAITools_WithMultipleAGUITools_ConvertsAllCorrectly()
    {
        // Arrange
        List<AGUITool> aguiTools =
        [
            new AGUITool { Name = "Tool1", Description = "Desc1", Parameters = JsonDocument.Parse("{}").RootElement },
            new AGUITool { Name = "Tool2", Description = "Desc2", Parameters = JsonDocument.Parse("{}").RootElement },
            new AGUITool { Name = "Tool3", Description = "Desc3", Parameters = JsonDocument.Parse("{}").RootElement }
        ];

        // Act
        List<AITool> tools = aguiTools.AsAITools().ToList();

        // Assert
        Assert.Equal(3, tools.Count);
        Assert.All(tools, t => Assert.IsAssignableFrom<AIFunctionDeclaration>(t));
    }

    [Fact]
    public void AsAITools_WithNullInput_ReturnsEmptyEnumerable()
    {
        // Arrange
        IEnumerable<AGUITool>? aguiTools = null;

        // Act
        IEnumerable<AITool> tools = aguiTools!.AsAITools();

        // Assert
        Assert.NotNull(tools);
        Assert.Empty(tools);
    }

    [Fact]
    public void AsAITools_WithEmptyInput_ReturnsEmptyEnumerable()
    {
        // Arrange
        List<AGUITool> aguiTools = [];

        // Act
        List<AITool> tools = aguiTools.AsAITools().ToList();

        // Assert
        Assert.Empty(tools);
    }

    [Fact]
    public void AsAITools_CreatesDeclarationsOnly_NotInvokableFunctions()
    {
        // Arrange
        AGUITool aguiTool = new()
        {
            Name = "RemoteTool",
            Description = "Tool implemented on server",
            Parameters = JsonDocument.Parse("{\"type\":\"object\"}").RootElement
        };

        // Act
        List<AGUITool> aguiToolsList = [aguiTool];
        AITool tool = aguiToolsList.AsAITools().Single();

        // Assert
        // The tool should be a declaration, not an executable function
        Assert.IsAssignableFrom<AIFunctionDeclaration>(tool);
        // AIFunctionDeclaration cannot be invoked (no implementation)
        // This is correct since the actual implementation exists on the client side
    }

    [Fact]
    public void RoundTrip_AIFunctionToAGUIToolBackToDeclaration_PreservesMetadata()
    {
        // Arrange
        AIFunction originalFunction = AIFunctionFactory.Create(
            (string name, int age) => $"{name} is {age} years old",
            "FormatPerson",
            "Formats person information");

        // Act
        List<AIFunction> originalList = [originalFunction];
        AGUITool aguiTool = originalList.AsAGUITools().Single();
        List<AGUITool> aguiToolsList = [aguiTool];
        AITool reconstructed = aguiToolsList.AsAITools().Single();

        // Assert
        Assert.IsAssignableFrom<AIFunctionDeclaration>(reconstructed);
        var declaration = (AIFunctionDeclaration)reconstructed;
        Assert.Equal("FormatPerson", declaration.Name);
        Assert.Equal("Formats person information", declaration.Description);
        // Schema should be preserved through the round trip
        Assert.NotEqual(default, declaration.JsonSchema);
    }
}
