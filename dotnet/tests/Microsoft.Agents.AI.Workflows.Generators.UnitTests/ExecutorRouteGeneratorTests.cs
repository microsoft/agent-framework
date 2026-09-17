// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;

namespace Microsoft.Agents.AI.Workflows.Generators.UnitTests;

/// <summary>
/// Tests for the ExecutorRouteGenerator source generator.
/// </summary>
public class ExecutorRouteGeneratorTests
{
    #region Single Handler Tests

    [Fact]
    public void SingleHandler_VoidReturn_GeneratesCorrectRoute()
    {
        var source = """
            using System.Threading;
            using System.Threading.Tasks;
            using Microsoft.Agents.AI.Workflows;

            namespace TestNamespace;

            public partial class TestExecutor : Executor
            {
                public TestExecutor() : base("test") { }

                [MessageHandler]
                private void HandleMessage(string message, IWorkflowContext context)
                {
                }
            }
            """;

        var result = GeneratorTestHelper.RunGenerator(source);

        Assert.Single(result.RunResult.GeneratedTrees);

        var generated = result.RunResult.GeneratedTrees[0];

        SyntaxTreeAssert.AddHandler(generated, "this.HandleMessage", "string");
    }

    [Fact]
    public void SingleHandler_ValueTaskReturn_GeneratesCorrectRoute()
    {
        var source = """
            using System.Threading;
            using System.Threading.Tasks;
            using Microsoft.Agents.AI.Workflows;

            namespace TestNamespace;

            public partial class TestExecutor : Executor
            {
                public TestExecutor() : base("test") { }

                [MessageHandler]
                private ValueTask HandleMessageAsync(string message, IWorkflowContext context)
                {
                    return default;
                }
            }
            """;

        var result = GeneratorTestHelper.RunGenerator(source);

        Assert.Single(result.RunResult.GeneratedTrees);

        var generated = result.RunResult.GeneratedTrees[0].ToString();
        Assert.Contains(".AddHandler<string>(this.HandleMessageAsync)", generated);
    }

    [Fact]
    public void SingleHandler_WithOutput_GeneratesCorrectRoute()
    {
        var source = """
            using System.Threading;
            using System.Threading.Tasks;
            using Microsoft.Agents.AI.Workflows;

            namespace TestNamespace;

            public partial class TestExecutor : Executor
            {
                public TestExecutor() : base("test") { }

                [MessageHandler]
                private ValueTask<int> HandleMessageAsync(string message, IWorkflowContext context)
                {
                    return new ValueTask<int>(42);
                }
            }
            """;

        var result = GeneratorTestHelper.RunGenerator(source);

        Assert.Single(result.RunResult.GeneratedTrees);

        var generated = result.RunResult.GeneratedTrees[0].ToString();
        Assert.Contains(".AddHandler<string, int>(this.HandleMessageAsync)", generated);
    }

    [Fact]
    public void SingleHandler_WithCancellationToken_GeneratesCorrectRoute()
    {
        var source = """
            using System.Threading;
            using System.Threading.Tasks;
            using Microsoft.Agents.AI.Workflows;

            namespace TestNamespace;

            public partial class TestExecutor : Executor
            {
                public TestExecutor() : base("test") { }

                [MessageHandler]
                private ValueTask HandleMessageAsync(string message, IWorkflowContext context, CancellationToken ct)
                {
                    return default;
                }
            }
            """;

        var result = GeneratorTestHelper.RunGenerator(source);

        Assert.Single(result.RunResult.GeneratedTrees);

        var generated = result.RunResult.GeneratedTrees[0].ToString();
        Assert.Contains(".AddHandler<string>(this.HandleMessageAsync)", generated);
    }

    #endregion

    #region Multiple Handler Tests

    [Fact]
    public void MultipleHandlers_GeneratesAllRoutes()
    {
        var source = """
            using System.Threading;
            using System.Threading.Tasks;
            using Microsoft.Agents.AI.Workflows;

            namespace TestNamespace;

            public partial class TestExecutor : Executor
            {
                public TestExecutor() : base("test") { }

                [MessageHandler]
                private void HandleString(string message, IWorkflowContext context) { }

                [MessageHandler]
                private void HandleInt(int message, IWorkflowContext context) { }

                [MessageHandler]
                private ValueTask<string> HandleDoubleAsync(double message, IWorkflowContext context)
                {
                    return new ValueTask<string>("result");
                }
            }
            """;

        var result = GeneratorTestHelper.RunGenerator(source);

        Assert.Single(result.RunResult.GeneratedTrees);

        var generated = result.RunResult.GeneratedTrees[0].ToString();
        Assert.Contains(".AddHandler<string>(this.HandleString)", generated);
        Assert.Contains(".AddHandler<int>(this.HandleInt)", generated);
        Assert.Contains(".AddHandler<double, string>(this.HandleDoubleAsync)", generated);
    }

    #endregion

    #region Yield and Send Type Tests

    [Fact]
    public void Handler_WithYieldTypes_GeneratesConfigureYieldTypes()
    {
        var source = """
            using System;
            using System.Threading;
            using System.Threading.Tasks;
            using Microsoft.Agents.AI.Workflows;

            namespace TestNamespace;

            public class OutputMessage { }

            public partial class TestExecutor : Executor
            {
                public TestExecutor() : base("test") { }

                [MessageHandler(Yield = new[] { typeof(OutputMessage) })]
                private void HandleMessage(string message, IWorkflowContext context) { }
            }
            """;

        var result = GeneratorTestHelper.RunGenerator(source);

        Assert.Single(result.RunResult.GeneratedTrees);

        var generated = result.RunResult.GeneratedTrees[0];

        SyntaxTreeAssert.RegisterYieldedOutputType(generated, "global::TestNamespace.OutputMessage");
    }

    [Fact]
    public void Handler_WithSendTypes_GeneratesConfigureSentTypes()
    {
        var source = """
            using System;
            using System.Threading;
            using System.Threading.Tasks;
            using Microsoft.Agents.AI.Workflows;

            namespace TestNamespace;

            public class SendMessage { }

            public partial class TestExecutor : Executor
            {
                public TestExecutor() : base("test") { }

                [MessageHandler(Send = new[] { typeof(SendMessage) })]
                private void HandleMessage(string message, IWorkflowContext context) { }
            }
            """;

        var result = GeneratorTestHelper.RunGenerator(source);

        Assert.Single(result.RunResult.GeneratedTrees);

        var generated = result.RunResult.GeneratedTrees[0];
        SyntaxTreeAssert.RegisterSentMessageType(generated, "global::TestNamespace.SendMessage");
    }

    [Fact]
    public void ClassLevel_SendsMessageAttribute_GeneratesConfigureSentTypes()
    {
        var source = """
            using System;
            using System.Threading;
            using System.Threading.Tasks;
            using Microsoft.Agents.AI.Workflows;

            namespace TestNamespace;

            public class BroadcastMessage { }

            [SendsMessage(typeof(BroadcastMessage))]
            public partial class TestExecutor : Executor
            {
                public TestExecutor() : base("test") { }

                [MessageHandler]
                private void HandleMessage(string message, IWorkflowContext context) { }
            }
            """;

        var result = GeneratorTestHelper.RunGenerator(source);

        Assert.Single(result.RunResult.GeneratedTrees);

        var generated = result.RunResult.GeneratedTrees[0];
        SyntaxTreeAssert.RegisterSentMessageType(generated, "global::TestNamespace.BroadcastMessage");
    }

    [Fact]
    public void ClassLevel_YieldsOutputAttribute_GeneratesConfigureYieldTypes()
    {
        var source = """
            using System;
            using System.Threading;
            using System.Threading.Tasks;
            using Microsoft.Agents.AI.Workflows;

            namespace TestNamespace;

            public class YieldedMessage { }

            [YieldsOutput(typeof(YieldedMessage))]
            public partial class TestExecutor : Executor
            {
                public TestExecutor() : base("test") { }

                [MessageHandler]
                private void HandleMessage(string message, IWorkflowContext context) { }
            }
            """;

        var result = GeneratorTestHelper.RunGenerator(source);

        Assert.Single(result.RunResult.GeneratedTrees);

        var generated = result.RunResult.GeneratedTrees[0];
        SyntaxTreeAssert.RegisterYieldedOutputType(generated, "global::TestNamespace.YieldedMessage");
    }

    #endregion

    #region Nested Class Tests

    [Fact]
    public void NestedClass_SingleLevel_GeneratesCorrectPartialHierarchy()
    {
        var source = """
            using System.Threading;
            using System.Threading.Tasks;
            using Microsoft.Agents.AI.Workflows;

            namespace TestNamespace;

            public partial class OuterClass
            {
                public partial class TestExecutor : Executor
                {
                    public TestExecutor() : base("test") { }

                    [MessageHandler]
                    private void HandleMessage(string message, IWorkflowContext context) { }
                }
            }
            """;

        var result = GeneratorTestHelper.RunGenerator(source);

        Assert.Single(result.RunResult.GeneratedTrees);
        Assert.Empty(result.RunResult.Diagnostics);

        var generated = result.RunResult.GeneratedTrees[0];

        SyntaxTreeAssert.HaveHierarchy(generated, "OuterClass", "TestExecutor");
        SyntaxTreeAssert.AddHandler(generated, "this.HandleMessage", "string");
    }

    [Fact]
    public void NestedClass_TwoLevels_GeneratesCorrectPartialHierarchy()
    {
        var source = """
            using System.Threading;
            using System.Threading.Tasks;
            using Microsoft.Agents.AI.Workflows;

            namespace TestNamespace;

            public partial class Outer
            {
                public partial class Inner
                {
                    public partial class TestExecutor : Executor
                    {
                        public TestExecutor() : base("test") { }

                        [MessageHandler]
                        private void HandleMessage(string message, IWorkflowContext context) { }
                    }
                }
            }
            """;

        var result = GeneratorTestHelper.RunGenerator(source);

        Assert.Single(result.RunResult.GeneratedTrees);
        Assert.Empty(result.RunResult.Diagnostics);

        var generated = result.RunResult.GeneratedTrees[0];

        SyntaxTreeAssert.HaveHierarchy(generated, "Outer", "Inner", "TestExecutor");
        SyntaxTreeAssert.AddHandler(generated, "this.HandleMessage", "string");
    }

    [Fact]
    public void NestedClass_ThreeLevels_GeneratesCorrectPartialHierarchy()
    {
        var source = """
            using System.Threading;
            using System.Threading.Tasks;
            using Microsoft.Agents.AI.Workflows;

            namespace TestNamespace;

            public partial class Level1
            {
                public partial class Level2
                {
                    public partial class Level3
                    {
                        public partial class TestExecutor : Executor
                        {
                            public TestExecutor() : base("test") { }

                            [MessageHandler]
                            private void HandleMessage(int message, IWorkflowContext context) { }
                        }
                    }
                }
            }
            """;

        var result = GeneratorTestHelper.RunGenerator(source);

        Assert.Single(result.RunResult.GeneratedTrees);
        Assert.Empty(result.RunResult.Diagnostics);

        var generated = result.RunResult.GeneratedTrees[0];

        SyntaxTreeAssert.HaveHierarchy(generated, "Level1", "Level2", "Level3", "TestExecutor");
        SyntaxTreeAssert.AddHandler(generated, "this.HandleMessage", "int");
    }

    [Fact]
    public void NestedClass_WithoutNamespace_GeneratesCorrectly()
    {
        var source = """
            using System.Threading;
            using System.Threading.Tasks;
            using Microsoft.Agents.AI.Workflows;

            public partial class OuterClass
            {
                public partial class TestExecutor : Executor
                {
                    public TestExecutor() : base("test") { }

                    [MessageHandler]
                    private void HandleMessage(string message, IWorkflowContext context) { }
                }
            }
            """;

        var result = GeneratorTestHelper.RunGenerator(source);

        Assert.Single(result.RunResult.GeneratedTrees);
        Assert.Empty(result.RunResult.Diagnostics);

        var generated = result.RunResult.GeneratedTrees[0];

        SyntaxTreeAssert.NotHaveNamespace(generated);
        SyntaxTreeAssert.HaveHierarchy(generated, "OuterClass", "TestExecutor");
        SyntaxTreeAssert.AddHandler(generated, "this.HandleMessage", "string");
    }

    [Fact]
    public void NestedClass_GeneratedCodeCompiles()
    {
        // This test verifies that the generated code actually compiles by checking
        // for compilation errors in the output (beyond our generator diagnostics)
        var source = """
            using System.Threading;
            using System.Threading.Tasks;
            using Microsoft.Agents.AI.Workflows;

            namespace TestNamespace;

            public partial class Outer
            {
                public partial class Inner
                {
                    public partial class TestExecutor : Executor
                    {
                        public TestExecutor() : base("test") { }

                        [MessageHandler]
                        private ValueTask<string> HandleMessage(int message, IWorkflowContext context)
                        {
                            return new ValueTask<string>("result");
                        }
                    }
                }
            }
            """;

        var result = GeneratorTestHelper.RunGenerator(source);

        // No generator diagnostics
        Assert.Empty(result.RunResult.Diagnostics);

        // Check that the combined compilation (source + generated) has no errors
        var compilationDiagnostics = result.OutputCompilation.GetDiagnostics()
            .Where(d => d.Severity == CodeAnalysis.DiagnosticSeverity.Error)
            .ToList();

        Assert.Empty(compilationDiagnostics ?? []);
    }

    [Fact]
    public void NestedClass_BraceBalancing_IsCorrect()
    {
        var source = """
            using System.Threading;
            using System.Threading.Tasks;
            using Microsoft.Agents.AI.Workflows;

            namespace TestNamespace;

            public partial class Outer
            {
                public partial class Inner
                {
                    public partial class TestExecutor : Executor
                    {
                        public TestExecutor() : base("test") { }

                        [MessageHandler]
                        private void HandleMessage(string message, IWorkflowContext context) { }
                    }
                }
            }
            """;

        var result = GeneratorTestHelper.RunGenerator(source);

        Assert.Single(result.RunResult.GeneratedTrees);

        var generated = result.RunResult.GeneratedTrees[0].ToString();

        // Count braces - they should be balanced
        var openBraces = generated.Count(c => c == '{');
        var closeBraces = generated.Count(c => c == '}');

        Assert.Equal(closeBraces, openBraces);

        // For Outer.Inner.TestExecutor, we expect:
        // - 1 for Outer class
        // - 1 for Inner class
        // - 1 for TestExecutor class
        // - 1 for ConfigureProtocol method
        // = 4 pairs minimum
        Assert.True(openBraces >= 4);
    }

    #endregion

    #region Multi-File Partial Class Tests

    [Fact]
    public void PartialClass_SplitAcrossFiles_GeneratesCorrectly()
    {
        // File 1: The "main" partial with constructor and base class
        var file1 = """
            using System.Threading;
            using System.Threading.Tasks;
            using Microsoft.Agents.AI.Workflows;

            namespace TestNamespace;

            public partial class TestExecutor : Executor
            {
                public TestExecutor() : base("test") { }

                // Some other business logic could be here
                public void DoSomething() { }
            }
            """;

        // File 2: Another partial with [MessageHandler] methods
        var file2 = """
            using System.Threading;
            using System.Threading.Tasks;
            using Microsoft.Agents.AI.Workflows;

            namespace TestNamespace;

            public partial class TestExecutor
            {
                [MessageHandler]
                private void HandleString(string message, IWorkflowContext context) { }

                [MessageHandler]
                private ValueTask HandleIntAsync(int message, IWorkflowContext context)
                {
                    return default;
                }
            }
            """;

        // Run generator with both files
        var result = GeneratorTestHelper.RunGenerator(file1, file2);

        // Should generate one file for the executor
        Assert.Single(result.RunResult.GeneratedTrees);
        Assert.Empty(result.RunResult.Diagnostics);

        var generated = result.RunResult.GeneratedTrees[0];

        // Should have both handlers registered
        SyntaxTreeAssert.AddHandler(generated, "this.HandleString", "string");
        SyntaxTreeAssert.AddHandler(generated, "this.HandleIntAsync", "int");

        // Verify the generated code compiles with all three partials combined
        var compilationErrors = result.OutputCompilation.GetDiagnostics()
            .Where(d => d.Severity == CodeAnalysis.DiagnosticSeverity.Error)
            .ToList();

        Assert.Empty(compilationErrors ?? []);
    }

    [Fact]
    public void PartialClass_HandlersInBothFiles_GeneratesAllHandlers()
    {
        // File 1: Partial with one handler
        var file1 = """
            using System.Threading;
            using System.Threading.Tasks;
            using Microsoft.Agents.AI.Workflows;

            namespace TestNamespace;

            public partial class TestExecutor : Executor
            {
                public TestExecutor() : base("test") { }

                [MessageHandler]
                private void HandleFromFile1(string message, IWorkflowContext context) { }
            }
            """;

        // File 2: Another partial with another handler
        var file2 = """
            using System.Threading;
            using System.Threading.Tasks;
            using Microsoft.Agents.AI.Workflows;

            namespace TestNamespace;

            public partial class TestExecutor
            {
                [MessageHandler]
                private void HandleFromFile2(int message, IWorkflowContext context) { }
            }
            """;

        var result = GeneratorTestHelper.RunGenerator(file1, file2);

        Assert.Single(result.RunResult.GeneratedTrees);
        Assert.Empty(result.RunResult.Diagnostics);

        var generated = result.RunResult.GeneratedTrees[0];

        // Both handlers from different files should be registered
        SyntaxTreeAssert.AddHandler(generated, "this.HandleFromFile1", "string");
        SyntaxTreeAssert.AddHandler(generated, "this.HandleFromFile2", "int");
    }

    [Fact]
    public void PartialClass_SendsYieldsInBothFiles_GeneratesAllOverrides()
    {
        // File 1: Partial with one handler
        var file1 = """
            using System.Threading;
            using System.Threading.Tasks;
            using Microsoft.Agents.AI.Workflows;

            namespace TestNamespace;

            [YieldsOutput(typeof(string))]
            [SendsMessage(typeof(int))]
            public partial class TestExecutor : Executor
            {
                public TestExecutor() : base("test") { }

                [MessageHandler]
                private void HandleFromFile1(string message, IWorkflowContext context) { }
            }
            """;

        // File 2: Another partial with another handler
        var file2 = """
            using System.Threading;
            using System.Threading.Tasks;
            using Microsoft.Agents.AI.Workflows;

            namespace TestNamespace;

            [YieldsOutput(typeof(int))]
            [SendsMessage(typeof(string))]
            public partial class TestExecutor
            {
                [MessageHandler]
                private void HandleFromFile2(int message, IWorkflowContext context) { }
            }
            """;

        var result = GeneratorTestHelper.RunGenerator(file1, file2);

        Assert.Single(result.RunResult.GeneratedTrees);
        Assert.Empty(result.RunResult.Diagnostics);

        var generated = result.RunResult.GeneratedTrees[0];

        // Verify SendsMessage and YieldsOutput from both partials are combined correctly
        SyntaxTreeAssert.RegisterSentMessageType(generated, "string");
        SyntaxTreeAssert.RegisterSentMessageType(generated, "int");
        SyntaxTreeAssert.RegisterYieldedOutputType(generated, "string");
        SyntaxTreeAssert.RegisterYieldedOutputType(generated, "int");
    }

    #endregion

    #region Diagnostic Tests

    [Fact]
    public void NonPartialClass_ProducesDiagnosticAndNoSource()
    {
        var source = """
            using System.Threading;
            using System.Threading.Tasks;
            using Microsoft.Agents.AI.Workflows;

            namespace TestNamespace;

            public class TestExecutor : Executor
            {
                public TestExecutor() : base("test") { }

                [MessageHandler]
                private void HandleMessage(string message, IWorkflowContext context) { }
            }
            """;

        var result = GeneratorTestHelper.RunGenerator(source);

        // Should produce MAFGENWF003 diagnostic
        Assert.Contains(result.RunResult.Diagnostics, d => d.Id == "MAFGENWF003");

        // Should NOT generate any source (to avoid CS0260)
        Assert.Empty(result.RunResult.GeneratedTrees);
    }

    [Fact]
    public void NonExecutorClass_ProducesDiagnostic()
    {
        var source = """
            using System.Threading;
            using System.Threading.Tasks;
            using Microsoft.Agents.AI.Workflows;

            namespace TestNamespace;

            public partial class NotAnExecutor
            {
                [MessageHandler]
                private void HandleMessage(string message, IWorkflowContext context) { }
            }
            """;

        var result = GeneratorTestHelper.RunGenerator(source);

        Assert.Contains(result.RunResult.Diagnostics, d => d.Id == "MAFGENWF004");
    }

    [Fact]
    public void StaticHandler_ProducesDiagnostic()
    {
        var source = """
            using System.Threading;
            using System.Threading.Tasks;
            using Microsoft.Agents.AI.Workflows;

            namespace TestNamespace;

            public partial class TestExecutor : Executor
            {
                public TestExecutor() : base("test") { }

                [MessageHandler]
                private static void HandleMessage(string message, IWorkflowContext context) { }
            }
            """;

        var result = GeneratorTestHelper.RunGenerator(source);

        Assert.Contains(result.RunResult.Diagnostics, d => d.Id == "MAFGENWF007");
    }

    [Fact]
    public void MissingWorkflowContext_ProducesDiagnostic()
    {
        var source = """
            using System.Threading;
            using System.Threading.Tasks;
            using Microsoft.Agents.AI.Workflows;

            namespace TestNamespace;

            public partial class TestExecutor : Executor
            {
                public TestExecutor() : base("test") { }

                [MessageHandler]
                private void HandleMessage(string message) { }
            }
            """;

        var result = GeneratorTestHelper.RunGenerator(source);

        Assert.Contains(result.RunResult.Diagnostics, d => d.Id == "MAFGENWF005");
    }

    [Fact]
    public void WrongSecondParameter_ProducesDiagnostic()
    {
        var source = """
            using System.Threading;
            using System.Threading.Tasks;
            using Microsoft.Agents.AI.Workflows;

            namespace TestNamespace;

            public partial class TestExecutor : Executor
            {
                public TestExecutor() : base("test") { }

                [MessageHandler]
                private void HandleMessage(string message, string notContext) { }
            }
            """;

        var result = GeneratorTestHelper.RunGenerator(source);

        Assert.Contains(result.RunResult.Diagnostics, d => d.Id == "MAFGENWF001");
    }

    #endregion

    #region No Generation Tests

    [Fact]
    public void ClassWithManualConfigureProtocol_DoesNotGenerate()
    {
        var source = """
            using System.Threading;
            using System.Threading.Tasks;
            using Microsoft.Agents.AI.Workflows;

            namespace TestNamespace;

            public partial class TestExecutor : Executor
            {
                public TestExecutor() : base("test") { }

                protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder)
                {
                    return protocolBuilder;
                }

                [MessageHandler]
                private void HandleMessage(string message, IWorkflowContext context) { }
            }
            """;

        var result = GeneratorTestHelper.RunGenerator(source);

        // Should produce diagnostic but not generate code
        Assert.Contains(result.RunResult.Diagnostics, d => d.Id == "MAFGENWF006");
        Assert.Empty(result.RunResult.GeneratedTrees);
    }

    [Fact]
    public void ClassWithNoMessageHandlers_DoesNotGenerate()
    {
        var source = """
            using System.Threading;
            using System.Threading.Tasks;
            using Microsoft.Agents.AI.Workflows;

            namespace TestNamespace;

            public partial class TestExecutor : Executor
            {
                public TestExecutor() : base("test") { }

                private void SomeOtherMethod(string message, IWorkflowContext context) { }
            }
            """;

        var result = GeneratorTestHelper.RunGenerator(source);

        Assert.Empty(result.RunResult.GeneratedTrees);
    }

    #endregion

    #region Protocol-Only Generation Tests

    [Fact]
    public void ProtocolOnly_MultipleSendsMessageAttributes_GeneratesAllTypes()
    {
        var source = """
            using System;
            using System.Threading;
            using System.Threading.Tasks;
            using Microsoft.Agents.AI.Workflows;

            namespace TestNamespace;

            public class MessageA { }
            public class MessageB { }
            public class MessageC { }

            [SendsMessage(typeof(MessageA))]
            [SendsMessage(typeof(MessageB))]
            [SendsMessage(typeof(MessageC))]
            public partial class TestExecutor : Executor
            {
                public TestExecutor() : base("test") { }
            }
            """;

        var result = GeneratorTestHelper.RunGenerator(source);

        Assert.Single(result.RunResult.GeneratedTrees);

        var generated = result.RunResult.GeneratedTrees[0];

        SyntaxTreeAssert.RegisterSentMessageType(generated, "global::TestNamespace.MessageA");
        SyntaxTreeAssert.RegisterSentMessageType(generated, "global::TestNamespace.MessageB");
        SyntaxTreeAssert.RegisterSentMessageType(generated, "global::TestNamespace.MessageC");
    }

    [Theory]
    [InlineData("SendsMessage")]
    [InlineData("YieldsOutput")]
    public void ProtocolOnly_NonPartialClass_ProducesProtocolDiagnostic(string attributeName)
    {
        var source = $$"""
            using System;
            using System.Threading;
            using System.Threading.Tasks;
            using Microsoft.Agents.AI.Workflows;

            namespace TestNamespace;

            public class BroadcastMessage { }

            [{{attributeName}}(typeof(BroadcastMessage))]
            public class TestExecutor : Executor
            {
                public TestExecutor() : base("test") { }
            }
            """;

        var result = GeneratorTestHelper.RunGenerator(source);

        Assert.Single(result.RunResult.Diagnostics);
        var diagnostic = result.RunResult.Diagnostics.Single();
        Assert.Equal("MAFGENWF008", diagnostic.Id);
        Assert.Equal("Class 'TestExecutor' uses [SendsMessage] or [YieldsOutput] but is not declared as partial", diagnostic.GetMessage());
        Assert.Empty(result.RunResult.GeneratedTrees);
    }

    [Fact]
    public void ProtocolOnly_NonPartialExecutorOfT_ProducesProtocolDiagnostic()
    {
        var source = """
            using System.Collections.Generic;
            using System.Threading;
            using System.Threading.Tasks;
            using Microsoft.Agents.AI.Workflows;

            namespace TestNamespace;

            [YieldsOutput(typeof(List<string>))]
            internal sealed class CompletionExecutor(string id) : Executor<List<ReduceComplete>>(id)
            {
                public override async ValueTask HandleAsync(
                    List<ReduceComplete> message,
                    IWorkflowContext context,
                    CancellationToken cancellationToken = default)
                {
                    List<string> filePaths = message.ConvertAll(result => result.FilePath);
                    await context.YieldOutputAsync(filePaths, cancellationToken);
                }
            }

            internal sealed record ReduceComplete(string FilePath);
            """;

        var result = GeneratorTestHelper.RunGenerator(source);

        Assert.Single(result.RunResult.Diagnostics);
        var diagnostic = result.RunResult.Diagnostics.Single();
        Assert.Equal("MAFGENWF008", diagnostic.Id);
        Assert.Equal("Class 'CompletionExecutor' uses [SendsMessage] or [YieldsOutput] but is not declared as partial", diagnostic.GetMessage());
        Assert.Empty(result.RunResult.GeneratedTrees);
    }

    [Theory]
    [InlineData("SendsMessage")]
    [InlineData("YieldsOutput")]
    public void ProtocolOnly_NonExecutorClass_ProducesProtocolDiagnostic(string attributeName)
    {
        var source = $$"""
            using System;
            using System.Threading;
            using System.Threading.Tasks;
            using Microsoft.Agents.AI.Workflows;

            namespace TestNamespace;

            public class BroadcastMessage { }

            [{{attributeName}}(typeof(BroadcastMessage))]
            public partial class NotAnExecutor
            {
            }
            """;

        var result = GeneratorTestHelper.RunGenerator(source);

        Assert.Single(result.RunResult.Diagnostics);
        var diagnostic = result.RunResult.Diagnostics.Single();
        Assert.Equal("MAFGENWF009", diagnostic.Id);
        Assert.Equal("Class 'NotAnExecutor' uses [SendsMessage] or [YieldsOutput] but does not derive from Executor", diagnostic.GetMessage());
        Assert.Empty(result.RunResult.GeneratedTrees);
    }

    [Fact]
    public void ProtocolOnly_NestedClass_GeneratesCorrectPartialHierarchy()
    {
        var source = """
            using System;
            using System.Threading;
            using System.Threading.Tasks;
            using Microsoft.Agents.AI.Workflows;

            namespace TestNamespace;

            public class BroadcastMessage { }

            public partial class OuterClass
            {
                [SendsMessage(typeof(BroadcastMessage))]
                public partial class TestExecutor : Executor
                {
                    public TestExecutor() : base("test") { }
                }
            }
            """;

        var result = GeneratorTestHelper.RunGenerator(source);

        Assert.Single(result.RunResult.GeneratedTrees);
        Assert.Empty(result.RunResult.Diagnostics);

        var generated = result.RunResult.GeneratedTrees[0];

        // Verify partial declarations are present
        SyntaxTreeAssert.HaveHierarchy(generated, "OuterClass", "TestExecutor");
        // Verify protocol types are generated
        SyntaxTreeAssert.RegisterSentMessageType(generated, "global::TestNamespace.BroadcastMessage");
    }

    [Fact]
    public void ProtocolOnly_GenericExecutor_GeneratesCorrectly()
    {
        var source = """
            using System;
            using System.Threading;
            using System.Threading.Tasks;
            using Microsoft.Agents.AI.Workflows;

            namespace TestNamespace;

            public class BroadcastMessage { }

            [SendsMessage(typeof(BroadcastMessage))]
            public partial class GenericExecutor<T> : Executor where T : class
            {
                public GenericExecutor() : base("generic") { }
            }
            """;

        var result = GeneratorTestHelper.RunGenerator(source);

        Assert.Single(result.RunResult.GeneratedTrees);

        var generated = result.RunResult.GeneratedTrees[0];

        SyntaxTreeAssert.HaveHierarchy(generated, "GenericExecutor<T>");
        SyntaxTreeAssert.RegisterSentMessageType(generated, "global::TestNamespace.BroadcastMessage");
    }

    [Fact]
    public void ProtocolOnly_DerivesFromExecutorOfT_GeneratesBaseCall()
    {
        // A protocol-only partial executor deriving from Executor<T>
        // has a base class that already overrides ConfigureProtocol. The generator must emit
        // "return base.ConfigureProtocol(protocolBuilder)" so inherited handler registrations
        // are preserved — not "return protocolBuilder" which silently drops them.
        var source = """
            using System;
            using System.Threading;
            using System.Threading.Tasks;
            using Microsoft.Agents.AI.Workflows;

            namespace TestNamespace;

            public class FeedbackResult { }

            [SendsMessage(typeof(FeedbackResult))]
            [YieldsOutput(typeof(string))]
            public partial class FeedbackExecutor : Executor<string>
            {
                public FeedbackExecutor() : base("feedback") { }

                public override System.Threading.Tasks.ValueTask HandleAsync(string message, IWorkflowContext context, System.Threading.CancellationToken cancellationToken = default)
                    => default;
            }
            """;

        var result = GeneratorTestHelper.RunGenerator(source);

        Assert.Single(result.RunResult.GeneratedTrees);
        Assert.Empty(result.RunResult.Diagnostics);

        var generated = result.RunResult.GeneratedTrees[0].ToString();

        // Base class Executor<T> overrides ConfigureProtocol, so the generated override
        // must chain to base to preserve the inherited handler registration.
        Assert.Contains("return base.ConfigureProtocol(protocolBuilder)", generated);
        Assert.Contains(".SendsMessage<global::TestNamespace.FeedbackResult>()", generated);
        Assert.Contains(".YieldsOutput<string>()", generated);
    }

    [Fact]
    public void ProtocolOnly_DerivesDirectlyFromExecutor_DoesNotGenerateBaseCall()
    {
        // A protocol-only partial executor deriving directly from Executor (abstract base
        // with no non-abstract ConfigureProtocol override) should generate "return protocolBuilder"
        // rather than "return base.ConfigureProtocol(protocolBuilder)".
        var source = """
            using System;
            using System.Threading;
            using System.Threading.Tasks;
            using Microsoft.Agents.AI.Workflows;

            namespace TestNamespace;

            public class BroadcastMessage { }

            [SendsMessage(typeof(BroadcastMessage))]
            public partial class BroadcastExecutor : Executor
            {
                public BroadcastExecutor() : base("broadcast") { }
            }
            """;

        var result = GeneratorTestHelper.RunGenerator(source);

        Assert.Single(result.RunResult.GeneratedTrees);
        Assert.Empty(result.RunResult.Diagnostics);

        var generated = result.RunResult.GeneratedTrees[0].ToString();

        // Executor's ConfigureProtocol is abstract — no base call needed.
        Assert.Contains("return protocolBuilder", generated);
        Assert.DoesNotContain("base.ConfigureProtocol", generated);
    }

    #endregion

    #region Generic Executor Tests

    [Fact]
    public void GenericExecutor_GeneratesCorrectly()
    {
        var source = """
            using System.Threading;
            using System.Threading.Tasks;
            using Microsoft.Agents.AI.Workflows;

            namespace TestNamespace;

            public partial class GenericExecutor<T> : Executor where T : class
            {
                public GenericExecutor() : base("generic") { }

                [MessageHandler]
                private void HandleMessage(T message, IWorkflowContext context) { }
            }
            """;

        var result = GeneratorTestHelper.RunGenerator(source);

        Assert.Single(result.RunResult.GeneratedTrees);

        var generated = result.RunResult.GeneratedTrees[0];

        SyntaxTreeAssert.HaveHierarchy(generated, "GenericExecutor<T>");
        SyntaxTreeAssert.AddHandler(generated, "this.HandleMessage", "T");
    }

    #endregion
}
