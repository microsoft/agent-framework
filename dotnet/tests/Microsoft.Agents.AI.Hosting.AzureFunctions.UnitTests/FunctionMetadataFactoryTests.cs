// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using Microsoft.Azure.Functions.Worker.Core.FunctionMetadata;

namespace Microsoft.Agents.AI.Hosting.AzureFunctions.UnitTests;

public sealed class FunctionMetadataFactoryTests
{
    [Fact]
    public void CreateEntityTrigger_SetsCorrectNameAndBindings()
    {
        DefaultFunctionMetadata metadata = FunctionMetadataFactory.CreateEntityTrigger("myAgent");

        Assert.Equal("dafx-myAgent", metadata.Name);
        Assert.Equal("dotnet-isolated", metadata.Language);
        Assert.Equal(BuiltInFunctions.RunAgentEntityFunctionEntryPoint, metadata.EntryPoint);
        Assert.NotNull(metadata.RawBindings);
        Assert.Equal(2, metadata.RawBindings.Count);
        Assert.Contains("entityTrigger", metadata.RawBindings[0]);
        Assert.Contains("durableClient", metadata.RawBindings[1]);
    }

    [Fact]
    public void CreateHttpTrigger_SetsCorrectNameRouteAndDefaults()
    {
        DefaultFunctionMetadata metadata = FunctionMetadataFactory.CreateHttpTrigger(
            "myWorkflow", "workflows/myWorkflow/run", BuiltInFunctions.RunWorkflowOrchestrationHttpFunctionEntryPoint);

        Assert.Equal("http-myWorkflow", metadata.Name);
        Assert.Equal("dotnet-isolated", metadata.Language);
        Assert.Equal(BuiltInFunctions.RunWorkflowOrchestrationHttpFunctionEntryPoint, metadata.EntryPoint);
        Assert.NotNull(metadata.RawBindings);
        Assert.Equal(3, metadata.RawBindings.Count);
        Assert.Contains("httpTrigger", metadata.RawBindings[0]);
        Assert.Contains("workflows/myWorkflow/run", metadata.RawBindings[0]);
        Assert.Contains("\"post\"", metadata.RawBindings[0]);
        Assert.Contains("http", metadata.RawBindings[1]);
        Assert.Contains("durableClient", metadata.RawBindings[2]);
    }

    [Fact]
    public void CreateHttpTrigger_RespectsCustomMethods()
    {
        DefaultFunctionMetadata metadata = FunctionMetadataFactory.CreateHttpTrigger(
            "status", "workflows/status/{runId}", BuiltInFunctions.GetWorkflowStatusHttpFunctionEntryPoint, methods: "\"get\"");

        Assert.NotNull(metadata.RawBindings);
        Assert.Contains("\"get\"", metadata.RawBindings[0]);
        Assert.DoesNotContain("\"post\"", metadata.RawBindings[0]);
    }

    [Fact]
    public void CreateActivityTrigger_SetsCorrectNameAndBindings()
    {
        DefaultFunctionMetadata metadata = FunctionMetadataFactory.CreateActivityTrigger("dafx-MyExecutor");

        Assert.Equal("dafx-MyExecutor", metadata.Name);
        Assert.Equal("dotnet-isolated", metadata.Language);
        Assert.Equal(BuiltInFunctions.InvokeWorkflowActivityFunctionEntryPoint, metadata.EntryPoint);
        Assert.NotNull(metadata.RawBindings);
        Assert.Equal(2, metadata.RawBindings.Count);
        Assert.Contains("activityTrigger", metadata.RawBindings[0]);
        Assert.Contains("durableClient", metadata.RawBindings[1]);
    }

    [Fact]
    public void CreateOrchestrationTrigger_SetsCorrectNameAndBindings()
    {
        DefaultFunctionMetadata metadata = FunctionMetadataFactory.CreateOrchestrationTrigger(
            "dafx-MyWorkflow", BuiltInFunctions.RunWorkflowOrchestrationFunctionEntryPoint);

        Assert.Equal("dafx-MyWorkflow", metadata.Name);
        Assert.Equal("dotnet-isolated", metadata.Language);
        Assert.Equal(BuiltInFunctions.RunWorkflowOrchestrationFunctionEntryPoint, metadata.EntryPoint);
        Assert.NotNull(metadata.RawBindings);
        Assert.Single(metadata.RawBindings);
        Assert.Contains("orchestrationTrigger", metadata.RawBindings[0]);
    }

    [Fact]
    public void CreateWorkflowMcpToolTrigger_SetsCorrectNameAndBindings()
    {
        DefaultFunctionMetadata metadata = FunctionMetadataFactory.CreateWorkflowMcpToolTrigger("Translate", "Translate text");

        Assert.Equal("mcptool-Translate", metadata.Name);
        Assert.Equal("dotnet-isolated", metadata.Language);
        Assert.Equal(BuiltInFunctions.RunWorkflowMcpToolFunctionEntryPoint, metadata.EntryPoint);
        Assert.NotNull(metadata.RawBindings);
        Assert.Equal(3, metadata.RawBindings.Count);

        // Verify all bindings are valid JSON
        foreach (string binding in metadata.RawBindings)
        {
            JsonDocument.Parse(binding);
        }

        // mcpToolTrigger binding
        Assert.Contains("mcpToolTrigger", metadata.RawBindings[0]);
        Assert.Contains("\"toolName\":\"Translate\"", metadata.RawBindings[0]);
        Assert.Contains("\"description\":\"Translate text\"", metadata.RawBindings[0]);
        Assert.Contains("toolProperties", metadata.RawBindings[0]);

        // mcpToolProperty binding for input
        Assert.Contains("mcpToolProperty", metadata.RawBindings[1]);
        Assert.Contains("\"propertyName\":\"input\"", metadata.RawBindings[1]);
        Assert.Contains("\"isRequired\":true", metadata.RawBindings[1]);

        // durableClient binding
        Assert.Contains("durableClient", metadata.RawBindings[2]);
    }

    [Fact]
    public void CreateWorkflowMcpToolTrigger_UsesDefaultDescription_WhenNull()
    {
        DefaultFunctionMetadata metadata = FunctionMetadataFactory.CreateWorkflowMcpToolTrigger("MyWorkflow", description: null);

        Assert.NotNull(metadata.RawBindings);
        Assert.Contains("Run the MyWorkflow workflow", metadata.RawBindings[0]);
    }
}
