// Copyright (c) Microsoft. All rights reserved.

using System;
using System.IO;
using System.Threading.Tasks;
using FluentAssertions;

namespace Microsoft.Agents.Workflows.UnitTests;

public class WorkflowVizTests
{
    private sealed class MockExecutor(string? id = null) : Executor(id)
    {
        protected override RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder) =>
            routeBuilder.AddHandler<string>((msg, ctx) => ctx.SendMessageAsync(msg));
    }

    private sealed class ListStrTargetExecutor(string? id = null) : Executor(id)
    {
        protected override RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder) =>
            routeBuilder.AddHandler<string[]>((msgs, ctx) => ctx.SendMessageAsync(string.Join(",", msgs)));
    }

    [Fact]
    public void Test_WorkflowViz_ToDotString_Basic()
    {
        // Create a simple workflow
        var executor1 = new MockExecutor("executor1");
        var executor2 = new MockExecutor("executor2");

        var workflow = new WorkflowBuilder("executor1")
            .AddEdge(executor1, executor2)
            .Build<string>();

        var viz = new WorkflowViz(workflow);
        var dotContent = viz.ToDotString();

        // Check that the DOT content contains expected elements
        dotContent.Should().Contain("digraph Workflow {");
        dotContent.Should().Contain("\"executor1\"");
        dotContent.Should().Contain("\"executor2\"");
        dotContent.Should().Contain("\"executor1\" -> \"executor2\"");
        dotContent.Should().Contain("fillcolor=lightgreen"); // Start executor styling
        dotContent.Should().Contain("(Start)");
    }

    [Fact]
    public async Task Test_WorkflowViz_Export_DotAsync()
    {
        // Create a simple workflow
        var executor1 = new MockExecutor("executor1");
        var executor2 = new MockExecutor("executor2");

        var workflow = new WorkflowBuilder("executor1")
            .AddEdge(executor1, executor2)
            .Build<string>();

        var viz = new WorkflowViz(workflow);

        // Test export without filename (returns temporary file path)
        var filePath = await viz.ExportAsync("dot");
        filePath.Should().EndWith(".dot");

        File.Exists(filePath).Should().BeTrue();
        var content = File.ReadAllText(filePath);

        content.Should().Contain("digraph Workflow {");
        content.Should().Contain("\"executor1\" -> \"executor2\"");

        // Clean up
        File.Delete(filePath);
    }

    [Fact]
    public async Task Test_WorkflowViz_Export_Dot_WithFilenameAsync()
    {
        // Create a simple workflow
        var executor1 = new MockExecutor("executor1");
        var executor2 = new MockExecutor("executor2");

        var workflow = new WorkflowBuilder("executor1")
            .AddEdge(executor1, executor2)
            .Build<string>();

        var viz = new WorkflowViz(workflow);

        // Test export with filename
        var tempPath = Path.GetTempPath();
        var outputFile = Path.Combine(tempPath, "test_workflow.dot");

        try
        {
            var resultPath = await viz.ExportAsync("dot", outputFile);

            resultPath.Should().Be(outputFile);
            File.Exists(outputFile).Should().BeTrue();

            var content = File.ReadAllText(outputFile);
            content.Should().Contain("digraph Workflow {");
            content.Should().Contain("\"executor1\" -> \"executor2\"");
        }
        finally
        {
            // Clean up
            if (File.Exists(outputFile))
            {
                File.Delete(outputFile);
            }
        }
    }

    [Fact]
    public void Test_WorkflowViz_Complex_Workflow()
    {
        // Test visualization of a more complex workflow
        var executor1 = new MockExecutor("start");
        var executor2 = new MockExecutor("middle1");
        var executor3 = new MockExecutor("middle2");
        var executor4 = new MockExecutor("end");

        var workflow = new WorkflowBuilder("start")
            .AddEdge(executor1, executor2)
            .AddEdge(executor1, executor3)
            .AddEdge(executor2, executor4)
            .AddEdge(executor3, executor4)
            .Build<string>();

        var viz = new WorkflowViz(workflow);
        var dotContent = viz.ToDotString();

        // Check all executors are present
        dotContent.Should().Contain("\"start\"");
        dotContent.Should().Contain("\"middle1\"");
        dotContent.Should().Contain("\"middle2\"");
        dotContent.Should().Contain("\"end\"");

        // Check all edges are present
        dotContent.Should().Contain("\"start\" -> \"middle1\"");
        dotContent.Should().Contain("\"start\" -> \"middle2\"");
        dotContent.Should().Contain("\"middle1\" -> \"end\"");
        dotContent.Should().Contain("\"middle2\" -> \"end\"");

        // Check start executor has special styling
        dotContent.Should().Contain("fillcolor=lightgreen");
    }

    [Fact]
    public async Task Test_WorkflowViz_Export_UnsupportedFormatAsync()
    {
        // Test that unsupported formats raise ArgumentException
        var executor1 = new MockExecutor("executor1");
        var executor2 = new MockExecutor("executor2");

        var workflow = new WorkflowBuilder("executor1")
            .AddEdge(executor1, executor2)
            .Build<string>();

        var viz = new WorkflowViz(workflow);

        var act = async () => await viz.ExportAsync("invalid");
        await act.Should().ThrowAsync<ArgumentException>()
            .WithMessage("*Unsupported format: invalid*");
    }

    [Fact]
    public void Test_WorkflowViz_Conditional_Edge()
    {
        // Test that conditional edges are rendered dashed with a label
        var start = new MockExecutor("start");
        var mid = new MockExecutor("mid");
        var end = new MockExecutor("end");

        // Condition that is never used during viz, but presence should mark the edge
        bool OnlyIfFoo(string? msg) => msg == "foo";

        var workflow = new WorkflowBuilder("start")
            .AddEdge<string>(start, mid, OnlyIfFoo)
            .AddEdge(mid, end)
            .Build<string>();

        var viz = new WorkflowViz(workflow);
        var dotContent = viz.ToDotString();

        // Conditional edge should be dashed and labeled
        dotContent.Should().Contain("\"start\" -> \"mid\" [style=dashed, label=\"conditional\"];");
        // Non-conditional edge should be plain
        dotContent.Should().Contain("\"mid\" -> \"end\"");
        dotContent.Should().NotContain("\"mid\" -> \"end\" [style=dashed");
    }

    [Fact]
    public void Test_WorkflowViz_FanIn_EdgeGroup()
    {
        // Test that fan-in edges render an intermediate node with label and routed edges
        var start = new MockExecutor("start");
        var s1 = new MockExecutor("s1");
        var s2 = new MockExecutor("s2");
        var t = new ListStrTargetExecutor("t");

        // Build a connected workflow: start fans out to s1 and s2, which then fan-in to t
        var workflow = new WorkflowBuilder("start")
            .AddFanOutEdge(start, s1, s2)
            .AddFanInEdge(t, s1, s2)  // AddFanInEdge(target, sources)
            .Build<string>();

        var viz = new WorkflowViz(workflow);
        var dotContent = viz.ToDotString();

        // There should be a single fan-in node with special styling and label
        var lines = dotContent.Split('\n');
        var fanInLines = Array.FindAll(lines, line =>
            line.Contains("shape=ellipse") && line.Contains("label=\"fan-in\""));
        fanInLines.Should().HaveCount(1);

        // Extract the intermediate node id from the line
        var fanInLine = fanInLines[0];
        var firstQuote = fanInLine.IndexOf('"');
        var secondQuote = fanInLine.IndexOf('"', firstQuote + 1);
        firstQuote.Should().BeGreaterThan(-1);
        secondQuote.Should().BeGreaterThan(-1);
        var fanInNodeId = fanInLine.Substring(firstQuote + 1, secondQuote - firstQuote - 1);
        fanInNodeId.Should().NotBeNullOrEmpty();

        // Edges should be routed through the intermediate node, not direct to target
        dotContent.Should().Contain($"\"s1\" -> \"{fanInNodeId}\";");
        dotContent.Should().Contain($"\"s2\" -> \"{fanInNodeId}\";");
        dotContent.Should().Contain($"\"{fanInNodeId}\" -> \"t\";");

        // Ensure direct edges are not present
        dotContent.Should().NotContain("\"s1\" -> \"t\"");
        dotContent.Should().NotContain("\"s2\" -> \"t\"");
    }

    [Fact]
    public async Task Test_WorkflowViz_SaveSvg_RequiresGraphvizAsync()
    {
        // Test SVG export - this requires graphviz to be installed
        var executor1 = new MockExecutor("executor1");
        var executor2 = new MockExecutor("executor2");

        var workflow = new WorkflowBuilder("executor1")
            .AddEdge(executor1, executor2)
            .Build<string>();

        var viz = new WorkflowViz(workflow);
        var tempFile = Path.GetTempFileName() + ".svg";

        try
        {
            // This will fail if graphviz is not installed
            var filePath = await viz.SaveSvgAsync(tempFile);
            filePath.Should().EndWith(".svg");
            File.Exists(filePath).Should().BeTrue();
        }
        catch (InvalidOperationException ex) when (ex.Message.Contains("Graphviz"))
        {
            // Expected if graphviz is not installed
            // This is fine for CI/CD environments
        }
        finally
        {
            if (File.Exists(tempFile))
            {
                File.Delete(tempFile);
            }
        }
    }

    [Fact]
    public async Task Test_WorkflowViz_SavePng_RequiresGraphvizAsync()
    {
        // Test PNG export - this requires graphviz to be installed
        var executor1 = new MockExecutor("executor1");
        var executor2 = new MockExecutor("executor2");

        var workflow = new WorkflowBuilder("executor1")
            .AddEdge(executor1, executor2)
            .Build<string>();

        var viz = new WorkflowViz(workflow);
        var tempFile = Path.GetTempFileName() + ".png";

        try
        {
            // This will fail if graphviz is not installed
            var filePath = await viz.SavePngAsync(tempFile);
            filePath.Should().EndWith(".png");
            File.Exists(filePath).Should().BeTrue();
        }
        catch (InvalidOperationException ex) when (ex.Message.Contains("Graphviz"))
        {
            // Expected if graphviz is not installed
            // This is fine for CI/CD environments
        }
        finally
        {
            if (File.Exists(tempFile))
            {
                File.Delete(tempFile);
            }
        }
    }

    [Fact]
    public async Task Test_WorkflowViz_SavePdf_RequiresGraphvizAsync()
    {
        // Test PDF export - this requires graphviz to be installed
        var executor1 = new MockExecutor("executor1");
        var executor2 = new MockExecutor("executor2");

        var workflow = new WorkflowBuilder("executor1")
            .AddEdge(executor1, executor2)
            .Build<string>();

        var viz = new WorkflowViz(workflow);
        var tempFile = Path.GetTempFileName() + ".pdf";

        try
        {
            // This will fail if graphviz is not installed
            var filePath = await viz.SavePdfAsync(tempFile);
            filePath.Should().EndWith(".pdf");
            File.Exists(filePath).Should().BeTrue();
        }
        catch (InvalidOperationException ex) when (ex.Message.Contains("Graphviz"))
        {
            // Expected if graphviz is not installed
            // This is fine for CI/CD environments
        }
        finally
        {
            if (File.Exists(tempFile))
            {
                File.Delete(tempFile);
            }
        }
    }

    [Fact]
    public void Test_WorkflowViz_NullWorkflow_ThrowsArgumentNullException()
    {
        // Test that null workflow throws ArgumentNullException
        Action act = () => _ = new WorkflowViz(null!);
        act.Should().Throw<ArgumentNullException>()
            .WithParameterName("workflow");
    }

    [Fact]
    public async Task Test_WorkflowViz_Export_NullFormat_ThrowsArgumentExceptionAsync()
    {
        var executor1 = new MockExecutor("executor1");
        var workflow = new WorkflowBuilder("executor1")
            .BindExecutor(executor1)
            .Build<string>();

        var viz = new WorkflowViz(workflow);

        var act = async () => await viz.ExportAsync(null!);
        await act.Should().ThrowAsync<ArgumentException>()
            .WithParameterName("format");
    }

    [Fact]
    public async Task Test_WorkflowViz_Export_EmptyFormat_ThrowsArgumentExceptionAsync()
    {
        var executor1 = new MockExecutor("executor1");
        var workflow = new WorkflowBuilder("executor1")
            .BindExecutor(executor1)
            .Build<string>();

        var viz = new WorkflowViz(workflow);

        var act = async () => await viz.ExportAsync("");
        await act.Should().ThrowAsync<ArgumentException>()
            .WithParameterName("format");
    }

    // Note: Sub-workflow tests are commented out as the current implementation
    // of TryGetNestedWorkflow returns false. These can be enabled once
    // WorkflowExecutor detection is implemented.

    /*
    [Fact]
    public void Test_WorkflowViz_SubWorkflow_Digraph()
    {
        // Test that WorkflowViz can visualize sub-workflows in DOT format
        // This test would require WorkflowExecutor implementation
        // Currently TryGetNestedWorkflow always returns false
    }

    [Fact]
    public void Test_WorkflowViz_Nested_SubWorkflows()
    {
        // Test visualization of deeply nested sub-workflows
        // This test would require WorkflowExecutor implementation
        // Currently TryGetNestedWorkflow always returns false
    }
    */

    [Fact]
    public void Test_WorkflowViz_FanOut_Edges()
    {
        // Test fan-out edge visualization
        var start = new MockExecutor("start");
        var target1 = new MockExecutor("target1");
        var target2 = new MockExecutor("target2");
        var target3 = new MockExecutor("target3");

        var workflow = new WorkflowBuilder("start")
            .AddFanOutEdge(start, target1, target2, target3)
            .Build<string>();

        var viz = new WorkflowViz(workflow);
        var dotContent = viz.ToDotString();

        // Check all fan-out edges are present
        dotContent.Should().Contain("\"start\" -> \"target1\"");
        dotContent.Should().Contain("\"start\" -> \"target2\"");
        dotContent.Should().Contain("\"start\" -> \"target3\"");
    }

    [Fact]
    public void Test_WorkflowViz_Mixed_EdgeTypes()
    {
        // Test workflow with mixed edge types (direct, conditional, fan-out, fan-in)
        var start = new MockExecutor("start");
        var a = new MockExecutor("a");
        var b = new MockExecutor("b");
        var c = new MockExecutor("c");
        var end = new ListStrTargetExecutor("end");

        bool Condition(string? msg) => msg?.Contains("test") ?? false;

        var workflow = new WorkflowBuilder("start")
            .AddEdge<string>(start, a, Condition) // Conditional edge
            .AddFanOutEdge(a, b, c) // Fan-out
            .AddFanInEdge(end, b, c) // Fan-in - AddFanInEdge(target, sources)
            .Build<string>();

        var viz = new WorkflowViz(workflow);
        var dotContent = viz.ToDotString();

        // Check conditional edge
        dotContent.Should().Contain("\"start\" -> \"a\" [style=dashed, label=\"conditional\"];");

        // Check fan-out edges
        dotContent.Should().Contain("\"a\" -> \"b\"");
        dotContent.Should().Contain("\"a\" -> \"c\"");

        // Check fan-in (should have intermediate node)
        dotContent.Should().Contain("shape=ellipse");
        dotContent.Should().Contain("label=\"fan-in\"");
    }

    [Fact]
    public void Test_WorkflowViz_SingleNode_Workflow()
    {
        // Test visualization of a single-node workflow
        var executor = new MockExecutor("single");

        var workflow = new WorkflowBuilder("single")
            .BindExecutor(executor)
            .Build<string>();

        var viz = new WorkflowViz(workflow);
        var dotContent = viz.ToDotString();

        // Check single node is present with start styling
        dotContent.Should().Contain("\"single\"");
        dotContent.Should().Contain("fillcolor=lightgreen");
        dotContent.Should().Contain("(Start)");
    }

    [Fact]
    public void Test_WorkflowViz_SelfLoop_Edge()
    {
        // Test visualization of self-loop edge
        var executor = new MockExecutor("loop");

        bool LoopCondition(string? msg) => (msg?.Length ?? 0) < 10;

        var workflow = new WorkflowBuilder("loop")
            .AddEdge<string>(executor, executor, LoopCondition)
            .Build<string>();

        var viz = new WorkflowViz(workflow);
        var dotContent = viz.ToDotString();

        // Check self-loop edge is present and conditional
        dotContent.Should().Contain("\"loop\" -> \"loop\" [style=dashed, label=\"conditional\"];");
    }

    [Fact]
    public async Task Test_WorkflowViz_Export_CaseInsensitiveAsync()
    {
        // Test that format parameter is case-insensitive
        var executor = new MockExecutor("test");
        var workflow = new WorkflowBuilder("test")
            .BindExecutor(executor)
            .Build<string>();
        var viz = new WorkflowViz(workflow);

        // Test with uppercase
        var filePath1 = await viz.ExportAsync("DOT");
        filePath1.Should().EndWith(".dot");
        File.Exists(filePath1).Should().BeTrue();
        File.Delete(filePath1);

        // Test with mixed case
        var filePath2 = await viz.ExportAsync("DoT");
        filePath2.Should().EndWith(".dot");
        File.Exists(filePath2).Should().BeTrue();
        File.Delete(filePath2);
    }
}
