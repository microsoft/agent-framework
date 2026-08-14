// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.UnitTests.Harness.FileMemory;

/// <summary>
/// Verifies that each file memory tool's description refers to arguments by the same
/// names that <see cref="AIFunctionFactory"/> exposes in the generated JSON schema.
/// </summary>
public class FileMemoryToolDescriptionSchemaTests
{
    [Theory]
    [InlineData(FileMemoryProvider.LsToolName)]
    [InlineData(FileMemoryProvider.GrepToolName)]
    public async Task FilteringTool_Description_UsesSchemaArgumentNameAsync(string toolName)
    {
        // Arrange
        AIFunction tool = await GetToolAsync(toolName);

        // Act
        List<string> schemaArguments = GetSchemaArgumentNames(tool);

        // Assert — the description and the generated schema agree on the filter argument name.
        Assert.Contains("globPattern", tool.Description);
        Assert.DoesNotContain("glob_pattern", tool.Description);
        Assert.Contains("globPattern", schemaArguments);
    }

    [Fact]
    public async Task ReplaceTool_Description_UsesSchemaArgumentNamesAsync()
    {
        // Arrange
        AIFunction tool = await GetToolAsync(FileMemoryProvider.ReplaceToolName);

        // Act
        List<string> schemaArguments = GetSchemaArgumentNames(tool);

        // Assert — the description and the generated schema agree on the replace argument names.
        Assert.Contains("oldString", tool.Description);
        Assert.Contains("newString", tool.Description);
        Assert.Contains("replaceAll", tool.Description);
        Assert.DoesNotContain("old_string", tool.Description);
        Assert.DoesNotContain("new_string", tool.Description);
        Assert.DoesNotContain("replace_all", tool.Description);
        Assert.Contains("oldString", schemaArguments);
        Assert.Contains("newString", schemaArguments);
        Assert.Contains("replaceAll", schemaArguments);
    }

    [Fact]
    public async Task ReplaceLinesTool_Description_KeepsExplicitJsonPropertyNamesAsync()
    {
        // Arrange
        AIFunction tool = await GetToolAsync(FileMemoryProvider.ReplaceLinesToolName);

        // Act
        List<string> schemaArguments = GetSchemaArgumentNames(tool);

        // Assert — line_number/new_line are mapped explicitly via JsonPropertyName, so the
        // description must keep referencing them as-is instead of a camelCase rename.
        Assert.Contains("line_number", tool.Description);
        Assert.Contains("new_line", tool.Description);
        Assert.Contains("line_number", schemaArguments);
        Assert.Contains("new_line", schemaArguments);
    }

    private static async Task<AIFunction> GetToolAsync(string toolName)
    {
        // Arrange
        var provider = new FileMemoryProvider(new InMemoryAgentFileStore());
        var agent = new Mock<AIAgent>().Object;
        var session = new ChatClientAgentSession();
#pragma warning disable MAAI001
        var context = new AIContextProvider.InvokingContext(agent, session, new AIContext());
#pragma warning restore MAAI001

        AIContext result = await provider.InvokingAsync(context);
        return (AIFunction)result.Tools!.First(t => t is AIFunction f && f.Name == toolName);
    }

    private static List<string> GetSchemaArgumentNames(AIFunction tool)
    {
        var names = new List<string>();
        if (tool.JsonSchema is JsonElement schema)
        {
            CollectPropertyNames(schema, names);
        }

        return names.Distinct().ToList();
    }

    private static void CollectPropertyNames(JsonElement element, List<string> names)
    {
        if (element.ValueKind == JsonValueKind.Object)
        {
            foreach (JsonProperty property in element.EnumerateObject())
            {
                if (property.Name == "properties")
                {
                    foreach (JsonProperty item in property.Value.EnumerateObject())
                    {
                        names.Add(item.Name);
                        CollectPropertyNames(item.Value, names);
                    }
                }
                else
                {
                    CollectPropertyNames(property.Value, names);
                }
            }
        }
        else if (element.ValueKind == JsonValueKind.Array)
        {
            foreach (JsonElement item in element.EnumerateArray())
            {
                CollectPropertyNames(item, names);
            }
        }
    }
}
