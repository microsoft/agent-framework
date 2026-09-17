// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

public class WorkflowVisualizerTests
{
    private sealed class MockExecutor(string id) : Executor(id)
    {
        protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder)
            => protocolBuilder.ConfigureRoutes(routeBuilder =>
                                               routeBuilder.AddHandler<string>((msg, ctx) => ctx.SendMessageAsync(msg)));
    }

    private sealed class ListStrTargetExecutor(string id) : Executor(id)
    {
        protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder)
            => protocolBuilder.ConfigureRoutes(routeBuilder =>
                                               routeBuilder.AddHandler<string[]>((msgs, ctx) => ctx.SendMessageAsync(string.Join(",", msgs))));
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
        Assert.Contains("digraph Workflow {", dotContent);
        Assert.Contains("\"executor1\"", dotContent);
        Assert.Contains("\"executor2\"", dotContent);
        Assert.Contains("\"executor1\" -> \"executor2\"", dotContent);
        Assert.Contains("fillcolor=lightgreen", dotContent); // Start executor styling
        Assert.Contains("(Start)", dotContent);
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
        Assert.Contains("\"start\"", dotContent);
        Assert.Contains("\"middle1\"", dotContent);
        Assert.Contains("\"middle2\"", dotContent);
        Assert.Contains("\"end\"", dotContent);

        // Check all edges are present
        Assert.Contains("\"start\" -> \"middle1\"", dotContent);
        Assert.Contains("\"start\" -> \"middle2\"", dotContent);
        Assert.Contains("\"middle1\" -> \"end\"", dotContent);
        Assert.Contains("\"middle2\" -> \"end\"", dotContent);

        // Check start executor has special styling
        Assert.Contains("fillcolor=lightgreen", dotContent);
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
        Assert.Contains("\"start\" -> \"mid\" [style=dashed, label=\"conditional\"];", dotContent);
        // Non-conditional edge should be plain
        Assert.Contains("\"mid\" -> \"end\"", dotContent);
        Assert.DoesNotContain("\"mid\" -> \"end\" [style=dashed", dotContent);
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
            .AddFanInBarrierEdge([s1, s2], t)  // AddFanInBarrierEdge(target, sources)
            .Build();

        var dotContent = workflow.ToDotString();

        // There should be a single fan-in node with special styling and label
        var lines = dotContent.Split('\n');
        var fanInLines = Array.FindAll(lines, line =>
            line.Contains("shape=ellipse") && line.Contains("label=\"fan-in\""));
        Assert.Single(fanInLines);

        // Extract the intermediate node id from the line
        var fanInLine = fanInLines[0];
        var firstQuote = fanInLine.IndexOf('"');
        var secondQuote = fanInLine.IndexOf('"', firstQuote + 1);
        Assert.True(firstQuote > (-1));
        Assert.True(secondQuote > (-1));
        var fanInNodeId = fanInLine.Substring(firstQuote + 1, secondQuote - firstQuote - 1);
        Assert.False(string.IsNullOrEmpty(fanInNodeId));

        // Edges should be routed through the intermediate node, not direct to target
        Assert.Contains($"\"s1\" -> \"{fanInNodeId}\";", dotContent);
        Assert.Contains($"\"s2\" -> \"{fanInNodeId}\";", dotContent);
        Assert.Contains($"\"{fanInNodeId}\" -> \"t\";", dotContent);

        // Ensure direct edges are not present
        Assert.DoesNotContain("\"s1\" -> \"t\"", dotContent);
        Assert.DoesNotContain("\"s2\" -> \"t\"", dotContent);
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
        Assert.Contains("\"start\" -> \"target1\"", dotContent);
        Assert.Contains("\"start\" -> \"target2\"", dotContent);
        Assert.Contains("\"start\" -> \"target3\"", dotContent);
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
            .AddFanInBarrierEdge([b, c], end) // Fan-in - AddFanInEdge(target, sources)
            .Build();

        var dotContent = workflow.ToDotString();

        // Check conditional edge
        Assert.Contains("\"start\" -> \"a\" [style=dashed, label=\"conditional\"];", dotContent);

        // Check fan-out edges
        Assert.Contains("\"a\" -> \"b\"", dotContent);
        Assert.Contains("\"a\" -> \"c\"", dotContent);

        // Check fan-in (should have intermediate node)
        Assert.Contains("shape=ellipse", dotContent);
        Assert.Contains("label=\"fan-in\"", dotContent);
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
        Assert.Contains("\"single\"", dotContent);
        Assert.Contains("fillcolor=lightgreen", dotContent);
        Assert.Contains("(Start)", dotContent);
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
        Assert.Contains("\"loop\" -> \"loop\" [style=dashed, label=\"conditional\"];", dotContent);
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
        Assert.Contains("flowchart TD", mermaidContent);
        Assert.Contains("executor1[\"executor1 (Start)\"]", mermaidContent);
        Assert.Contains("executor2[\"executor2\"]", mermaidContent);
        Assert.Contains("executor1 --> executor2", mermaidContent);
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

        // Conditional edge should be dotted with label (using .-> not .-->)
        Assert.Contains("-. conditional .-> ", mermaidContent);
        // Non-conditional edge should be a specific solid arrow
        Assert.Contains("mid --> end", mermaidContent);
        // Display labels should be present
        Assert.Contains("\"start (Start)\"", mermaidContent);
        Assert.Contains("\"mid\"", mermaidContent);
        Assert.Contains("\"end\"", mermaidContent);
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
            .AddFanInBarrierEdge([s1, s2], t)
            .Build();

        var mermaidContent = workflow.ToMermaidString();

        // There should be a fan-in node with special styling
        var lines = mermaidContent.Split('\n');
        var fanInLines = Array.FindAll(lines, line => line.Contains("((fan-in))"));
        Assert.Single(fanInLines);

        // Extract the intermediate fan-in node id from the line
        var fanInLine = fanInLines[0].Trim();
        var fanInNodeId = fanInLine.Substring(0, fanInLine.IndexOf("((fan-in))", StringComparison.Ordinal)).Trim();
        Assert.False(string.IsNullOrEmpty(fanInNodeId));

        // Edges should be routed through the intermediate node
        Assert.Contains($"s1 --> {fanInNodeId}", mermaidContent);
        Assert.Contains($"s2 --> {fanInNodeId}", mermaidContent);
        Assert.Contains($"{fanInNodeId} --> t", mermaidContent);

        // Ensure direct edges are not present
        Assert.DoesNotContain("s1 --> t", mermaidContent);
        Assert.DoesNotContain("s2 --> t", mermaidContent);

        // Display labels should be present
        Assert.Contains("\"start (Start)\"", mermaidContent);
        Assert.Contains("\"s1\"", mermaidContent);
        Assert.Contains("\"s2\"", mermaidContent);
        Assert.Contains("\"t\"", mermaidContent);

        // All node IDs should be safe aliases (ASCII-only identifiers)
        foreach (var line in mermaidContent.Split('\n'))
        {
            var trimmed = line.Trim();
            if (trimmed.Contains("[\"") || trimmed.Contains("(("))
            {
                var bracketIdx = trimmed.IndexOfAny(['[', '(']);
                var nodeId = trimmed.Substring(0, bracketIdx);
                Assert.Matches("^[a-zA-Z_][a-zA-Z0-9_]*$", nodeId);
            }
        }
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

        // Check display labels are present
        Assert.Contains("\"start (Start)\"", mermaidContent);
        Assert.Contains("\"middle1\"", mermaidContent);
        Assert.Contains("\"middle2\"", mermaidContent);
        Assert.Contains("\"end\"", mermaidContent);

        // Check that sanitized IDs are used and all edges connect them
        Assert.Contains("start[\"start (Start)\"]", mermaidContent);
        Assert.Contains("start --> middle1", mermaidContent);
        Assert.Contains("start --> middle2", mermaidContent);
        Assert.Contains("middle1 --> end", mermaidContent);
        Assert.Contains("middle2 --> end", mermaidContent);
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
            .AddFanInBarrierEdge([b, c], end) // Fan-in
            .Build();

        var mermaidContent = workflow.ToMermaidString();

        // Check conditional edge uses correct syntax (.-> not .-->)
        Assert.Contains("-. conditional .->", mermaidContent);
        Assert.DoesNotContain(".-->", mermaidContent);

        // Check fan-in (should have intermediate node)
        Assert.Contains("((fan-in))", mermaidContent);

        // Display labels should be present
        Assert.Contains("\"start (Start)\"", mermaidContent);
        Assert.Contains("\"a\"", mermaidContent);
        Assert.Contains("\"b\"", mermaidContent);
        Assert.Contains("\"c\"", mermaidContent);
        Assert.Contains("\"end\"", mermaidContent);
    }

    [Fact]
    public void Test_WorkflowViz_Mermaid_Edge_Label_With_Pipe()
    {
        // Test that pipe characters in labels are properly escaped
        var start = new MockExecutor("start");
        var end = new MockExecutor("end");

        var workflow = new WorkflowBuilder("start")
            .AddEdge(start, end, label: "High | Low Priority")
            .Build();

        var mermaidContent = workflow.ToMermaidString();

        // Should escape pipe character
        Assert.Contains("-->|High &#124; Low Priority|", mermaidContent);
        // Should not contain unescaped pipe that would break syntax
        Assert.DoesNotContain("-->|High | Low", mermaidContent);
    }

    [Fact]
    public void Test_WorkflowViz_Mermaid_Edge_Label_With_Special_Chars()
    {
        // Test that special characters are properly escaped
        var start = new MockExecutor("start");
        var end = new MockExecutor("end");

        var workflow = new WorkflowBuilder("start")
            .AddEdge(start, end, label: "Score >= 90 & < 100")
            .Build();

        var mermaidContent = workflow.ToMermaidString();

        // Should escape special characters
        Assert.Contains("&amp;", mermaidContent);
        Assert.Contains("&gt;", mermaidContent);
        Assert.Contains("&lt;", mermaidContent);
    }

    [Fact]
    public void Test_WorkflowViz_Mermaid_Edge_Label_With_Newline()
    {
        // Test that newlines are converted to <br/>
        var start = new MockExecutor("start");
        var end = new MockExecutor("end");

        var workflow = new WorkflowBuilder("start")
            .AddEdge(start, end, label: "Line 1\nLine 2")
            .Build();

        var mermaidContent = workflow.ToMermaidString();

        // Should convert newline to <br/>
        Assert.Contains("Line 1<br/>Line 2", mermaidContent);
        // Should not contain literal newline in the label (but the overall output has newlines between statements)
        Assert.DoesNotContain("Line 1\nLine 2", mermaidContent);
    }

    [Fact]
    public void Test_WorkflowViz_Mermaid_ConditionalEdge_ArrowSyntax()
    {
        // Conditional edges must use "-. label .->" (not ".-->") which is the correct
        // Mermaid syntax for dotted arrows with labels.
        var start = new MockExecutor("start");
        var mid = new MockExecutor("mid");

        static bool Condition(string? msg) => msg == "foo";

        var workflow = new WorkflowBuilder("start")
            .AddEdge<string>(start, mid, Condition)
            .Build();

        var mermaidContent = workflow.ToMermaidString();

        // The output should use ".->" not ".-->" for conditional (dotted) edges
        Assert.DoesNotContain(".-->", mermaidContent);
        Assert.Contains("-. conditional .->", mermaidContent);
    }

    [Fact]
    public void Test_WorkflowViz_Mermaid_IdentifiersWithSpaces()
    {
        // Identifiers with spaces must not be used directly as Mermaid node IDs
        // because spaces cause rendering errors.
        var executor1 = new MockExecutor("1. User input");
        var executor2 = new MockExecutor("2. Process data");

        var workflow = new WorkflowBuilder("1. User input")
            .AddEdge(executor1, executor2)
            .Build();

        var mermaidContent = workflow.ToMermaidString();

        // Node definitions should use safe aliases as IDs (no spaces), with display names in quotes
        // Bad: '1. User input["1. User input (Start)"]' — spaces in ID break Mermaid
        // Good: 'n_1_User_input["1. User input (Start)"]' — alias ID is safe and sanitized

        // Each node definition line (containing ["..."]) should have a space-free ID before the bracket
        foreach (var line in mermaidContent.Split('\n'))
        {
            var trimmed = line.Trim();
            if (trimmed.Contains("[\""))
            {
                var bracketIdx = trimmed.IndexOf('[');
                var nodeId = trimmed.Substring(0, bracketIdx);
                Assert.DoesNotContain(" ", nodeId);
            }
        }
    }

    [Fact]
    public void Test_WorkflowViz_Mermaid_IdentifiersWithUnicode()
    {
        // Non-ASCII characters (e.g. Japanese) in identifiers cause Mermaid rendering errors.
        var executor1 = new MockExecutor("ユーザー入力");
        var executor2 = new MockExecutor("データ処理");

        var workflow = new WorkflowBuilder("ユーザー入力")
            .AddEdge(executor1, executor2)
            .Build();

        var mermaidContent = workflow.ToMermaidString();

        // The display labels should contain the original names
        Assert.Contains("ユーザー入力", mermaidContent);
        Assert.Contains("データ処理", mermaidContent);

        // But node IDs (before the bracket) should be safe ASCII-only identifiers
        foreach (var line in mermaidContent.Split('\n'))
        {
            var trimmed = line.Trim();
            if (trimmed.Contains("[\""))
            {
                var bracketIdx = trimmed.IndexOf('[');
                var nodeId = trimmed.Substring(0, bracketIdx);
                // Node ID should start with a letter or underscore, followed by ASCII alphanumeric or underscores
                Assert.Matches("^[a-zA-Z_][a-zA-Z0-9_]*$", nodeId);
            }
        }
    }
}
