// Copyright (c) Microsoft. All rights reserved.

using System;
using FluentAssertions;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

public class WorkflowVisualizerTests
{
    private sealed class MockExecutor(string id) : Executor(id)
    {
        protected override RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder) =>
            routeBuilder.AddHandler<string>((msg, ctx) => ctx.SendMessageAsync(msg));
    }

    private sealed class ListStrTargetExecutor(string id) : Executor(id)
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
            .Build();

        var dotContent = workflow.ToDotString();

        // Check that the DOT content contains expected elements
        dotContent.Should().Contain("digraph Workflow {");
        dotContent.Should().Contain("\"executor1\"");
        dotContent.Should().Contain("\"executor2\"");
        dotContent.Should().Contain("\"executor1\" -> \"executor2\"");
        dotContent.Should().Contain("fillcolor=lightgreen"); // Start executor styling
        dotContent.Should().Contain("(Start)");
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
            .Build();

        var dotContent = workflow.ToDotString();

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
    public void Test_WorkflowViz_Conditional_Edge()
    {
        // Test that conditional edges are rendered dashed with a label
        var start = new MockExecutor("start");
        var mid = new MockExecutor("mid");
        var end = new MockExecutor("end");

        // Condition that is never used during viz, but presence should mark the edge
        static bool OnlyIfFoo(string? msg) => msg == "foo";

        var workflow = new WorkflowBuilder("start")
            .AddEdge<string>(start, mid, OnlyIfFoo)
            .AddEdge(mid, end)
            .Build();

        var dotContent = workflow.ToDotString();

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
            .AddFanOutEdge(start, [s1, s2])
            .AddFanInEdge([s1, s2], t)  // AddFanInEdge(target, sources)
            .Build();

        var dotContent = workflow.ToDotString();

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
            .AddFanOutEdge(start, [target1, target2, target3])
            .Build();

        var dotContent = workflow.ToDotString();

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

        static bool Condition(string? msg) => msg?.Contains("test") ?? false;

        var workflow = new WorkflowBuilder("start")
            .AddEdge<string>(start, a, Condition) // Conditional edge
            .AddFanOutEdge(a, [b, c]) // Fan-out
            .AddFanInEdge([b, c], end) // Fan-in - AddFanInEdge(target, sources)
            .Build();

        var dotContent = workflow.ToDotString();

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
            .Build();

        var dotContent = workflow.ToDotString();

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

        static bool LoopCondition(string? msg) => (msg?.Length ?? 0) < 10;

        var workflow = new WorkflowBuilder("loop")
            .AddEdge<string>(executor, executor, LoopCondition)
            .Build();

        var dotContent = workflow.ToDotString();

        // Check self-loop edge is present and conditional
        dotContent.Should().Contain("\"loop\" -> \"loop\" [style=dashed, label=\"conditional\"];");
    }

    [Fact]
    public void Test_WorkflowViz_ToMermaidString_Basic()
    {
        // Test that WorkflowViz can generate a Mermaid diagram
        var executor1 = new MockExecutor("executor1");
        var executor2 = new MockExecutor("executor2");

        var workflow = new WorkflowBuilder("executor1")
            .AddEdge(executor1, executor2)
            .Build();

        var mermaidContent = workflow.ToMermaidString();

        // Check that the Mermaid content contains expected elements
        mermaidContent.Should().Contain("flowchart TD");
        mermaidContent.Should().Contain("executor1[\"executor1 (Start)\"]");
        mermaidContent.Should().Contain("executor2[\"executor2\"]");
        mermaidContent.Should().Contain("executor1 --> executor2");
    }

    [Fact]
    public void Test_WorkflowViz_Mermaid_Conditional_Edge()
    {
        // Test that conditional edges are rendered with dotted lines and labels in Mermaid
        var start = new MockExecutor("start");
        var mid = new MockExecutor("mid");
        var end = new MockExecutor("end");

        static bool OnlyIfFoo(string? msg) => msg == "foo";

        var workflow = new WorkflowBuilder("start")
            .AddEdge<string>(start, mid, OnlyIfFoo)
            .AddEdge(mid, end)
            .Build();

        var mermaidContent = workflow.ToMermaidString();

        // Conditional edge should be dotted with label
        mermaidContent.Should().Contain("start -. conditional .--> mid");
        // Non-conditional edge should be solid
        mermaidContent.Should().Contain("mid --> end");
        mermaidContent.Should().NotContain("end -. conditional");
    }

    [Fact]
    public void Test_WorkflowViz_Mermaid_FanIn_EdgeGroup()
    {
        // Test that fan-in edges render an intermediate node with label and routed edges in Mermaid
        var start = new MockExecutor("start");
        var s1 = new MockExecutor("s1");
        var s2 = new MockExecutor("s2");
        var t = new ListStrTargetExecutor("t");

        var workflow = new WorkflowBuilder("start")
            .AddFanOutEdge(start, [s1, s2])
            .AddFanInEdge([s1, s2], t)
            .Build();

        var mermaidContent = workflow.ToMermaidString();

        // There should be a fan-in node with special styling
        var lines = mermaidContent.Split('\n');
        var fanInLines = Array.FindAll(lines, line => line.Contains("((fan-in))"));
        fanInLines.Should().HaveCount(1);

        // Extract the intermediate node id from the line
        var fanInLine = fanInLines[0].Trim();
        var fanInNodeId = fanInLine.Substring(0, fanInLine.IndexOf("((fan-in))", StringComparison.Ordinal)).Trim();
        fanInNodeId.Should().NotBeNullOrEmpty();

        // Edges should be routed through the intermediate node
        mermaidContent.Should().Contain($"s1 --> {fanInNodeId}");
        mermaidContent.Should().Contain($"s2 --> {fanInNodeId}");
        mermaidContent.Should().Contain($"{fanInNodeId} --> t");

        // Ensure direct edges are not present
        mermaidContent.Should().NotContain("s1 --> t");
        mermaidContent.Should().NotContain("s2 --> t");
    }

    [Fact]
    public void Test_WorkflowViz_Mermaid_Complex_Workflow()
    {
        // Test Mermaid visualization of a more complex workflow
        var executor1 = new MockExecutor("start");
        var executor2 = new MockExecutor("middle1");
        var executor3 = new MockExecutor("middle2");
        var executor4 = new MockExecutor("end");

        var workflow = new WorkflowBuilder("start")
            .AddEdge(executor1, executor2)
            .AddEdge(executor1, executor3)
            .AddEdge(executor2, executor4)
            .AddEdge(executor3, executor4)
            .Build();

        var mermaidContent = workflow.ToMermaidString();

        // Check all executors are present
        mermaidContent.Should().Contain("start[\"start (Start)\"]");
        mermaidContent.Should().Contain("middle1[\"middle1\"]");
        mermaidContent.Should().Contain("middle2[\"middle2\"]");
        mermaidContent.Should().Contain("end[\"end\"]");

        // Check all edges are present
        mermaidContent.Should().Contain("start --> middle1");
        mermaidContent.Should().Contain("start --> middle2");
        mermaidContent.Should().Contain("middle1 --> end");
        mermaidContent.Should().Contain("middle2 --> end");
    }

    [Fact]
    public void Test_WorkflowViz_Mermaid_Mixed_EdgeTypes()
    {
        // Test Mermaid workflow with mixed edge types (direct, conditional, fan-out, fan-in)
        var start = new MockExecutor("start");
        var a = new MockExecutor("a");
        var b = new MockExecutor("b");
        var c = new MockExecutor("c");
        var end = new ListStrTargetExecutor("end");

        static bool Condition(string? msg) => msg?.Contains("test") ?? false;

        var workflow = new WorkflowBuilder("start")
            .AddEdge<string>(start, a, Condition) // Conditional edge
            .AddFanOutEdge(a, [b, c]) // Fan-out
            .AddFanInEdge([b, c], end) // Fan-in
            .Build();

        var mermaidContent = workflow.ToMermaidString();

        // Check conditional edge
        mermaidContent.Should().Contain("start -. conditional .--> a");

        // Check fan-out edges
        mermaidContent.Should().Contain("a --> b");
        mermaidContent.Should().Contain("a --> c");

        // Check fan-in (should have intermediate node)
        mermaidContent.Should().Contain("((fan-in))");
    }
}
