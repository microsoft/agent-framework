// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using FluentAssertions;

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

        result.RunResult.GeneratedTrees.Should().HaveCount(1);

        var generated = result.RunResult.GeneratedTrees[0];

        generated.Should().AddHandler("this.HandleMessage", "string");
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

        result.RunResult.GeneratedTrees.Should().HaveCount(1);

        var generated = result.RunResult.GeneratedTrees[0].ToString();
        generated.Should().Contain(".AddHandler<string>(this.HandleMessageAsync)");
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

        result.RunResult.GeneratedTrees.Should().HaveCount(1);

        var generated = result.RunResult.GeneratedTrees[0].ToString();
        generated.Should().Contain(".AddHandler<string, int>(this.HandleMessageAsync)");
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

        result.RunResult.GeneratedTrees.Should().HaveCount(1);

        var generated = result.RunResult.GeneratedTrees[0].ToString();
        generated.Should().Contain(".AddHandler<string>(this.HandleMessageAsync)");
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

        result.RunResult.GeneratedTrees.Should().HaveCount(1);

        var generated = result.RunResult.GeneratedTrees[0].ToString();
        generated.Should().Contain(".AddHandler<string>(this.HandleString)");
        generated.Should().Contain(".AddHandler<int>(this.HandleInt)");
        generated.Should().Contain(".AddHandler<double, string>(this.HandleDoubleAsync)");
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

        result.RunResult.GeneratedTrees.Should().HaveCount(1);

        var generated = result.RunResult.GeneratedTrees[0];

        generated.Should().RegisterYieldedOutputType("global::TestNamespace.OutputMessage");
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

        result.RunResult.GeneratedTrees.Should().HaveCount(1);

        var generated = result.RunResult.GeneratedTrees[0];
        generated.Should().RegisterSentMessageType("global::TestNamespace.SendMessage");
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

        result.RunResult.GeneratedTrees.Should().HaveCount(1);

        var generated = result.RunResult.GeneratedTrees[0];
        generated.Should().RegisterSentMessageType("global::TestNamespace.BroadcastMessage");
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

        result.RunResult.GeneratedTrees.Should().HaveCount(1);

        var generated = result.RunResult.GeneratedTrees[0];
        generated.Should().RegisterYieldedOutputType("global::TestNamespace.YieldedMessage");
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

        result.RunResult.GeneratedTrees.Should().HaveCount(1);
        result.RunResult.Diagnostics.Should().BeEmpty();

        var generated = result.RunResult.GeneratedTrees[0];

        generated.Should().HaveHierarchy("OuterClass", "TestExecutor")
                      .And.AddHandler("this.HandleMessage", "string");
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

        result.RunResult.GeneratedTrees.Should().HaveCount(1);
        result.RunResult.Diagnostics.Should().BeEmpty();

        var generated = result.RunResult.GeneratedTrees[0];

        generated.Should().HaveHierarchy("Outer", "Inner", "TestExecutor")
                      .And.AddHandler("this.HandleMessage", "string");
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

        result.RunResult.GeneratedTrees.Should().HaveCount(1);
        result.RunResult.Diagnostics.Should().BeEmpty();

        var generated = result.RunResult.GeneratedTrees[0];

        generated.Should().HaveHierarchy("Level1", "Level2", "Level3", "TestExecutor")
                      .And.AddHandler("this.HandleMessage", "int");
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

        result.RunResult.GeneratedTrees.Should().HaveCount(1);
        result.RunResult.Diagnostics.Should().BeEmpty();

        var generated = result.RunResult.GeneratedTrees[0];

        generated.Should().NotHaveNamespace()
                      .And.HaveHierarchy("OuterClass", "TestExecutor")
                      .And.AddHandler("this.HandleMessage", "string");
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
        result.RunResult.Diagnostics.Should().BeEmpty();

        // Check that the combined compilation (source + generated) has no errors
        var compilationDiagnostics = result.OutputCompilation.GetDiagnostics()
            .Where(d => d.Severity == CodeAnalysis.DiagnosticSeverity.Error)
            .ToList();

        compilationDiagnostics.Should().BeEmpty(
            "generated code for nested classes should compile without errors");
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

        result.RunResult.GeneratedTrees.Should().HaveCount(1);

        var generated = result.RunResult.GeneratedTrees[0].ToString();

        // Count braces - they should be balanced
        var openBraces = generated.Count(c => c == '{');
        var closeBraces = generated.Count(c => c == '}');

        openBraces.Should().Be(closeBraces, "generated code should have balanced braces");

        // For Outer.Inner.TestExecutor, we expect:
        // - 1 for Outer class
        // - 1 for Inner class
        // - 1 for TestExecutor class
        // - 1 for ConfigureProtocol method
        // = 4 pairs minimum
        openBraces.Should().BeGreaterThanOrEqualTo(4, "should have braces for all nested classes and method");
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
        result.RunResult.GeneratedTrees.Should().HaveCount(1);
        result.RunResult.Diagnostics.Should().BeEmpty();

        var generated = result.RunResult.GeneratedTrees[0];

        // Should have both handlers registered
        generated.Should().AddHandler("this.HandleString", "string")
                      .And.AddHandler("this.HandleIntAsync", "int");

        // Verify the generated code compiles with all three partials combined
        var compilationErrors = result.OutputCompilation.GetDiagnostics()
            .Where(d => d.Severity == CodeAnalysis.DiagnosticSeverity.Error)
            .ToList();

        compilationErrors.Should().BeEmpty(
            "generated partial should compile correctly with the other partial files");
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

        result.RunResult.GeneratedTrees.Should().HaveCount(1);
        result.RunResult.Diagnostics.Should().BeEmpty();

        var generated = result.RunResult.GeneratedTrees[0];

        // Both handlers from different files should be registered
        generated.Should().AddHandler("this.HandleFromFile1", "string")
                      .And.AddHandler("this.HandleFromFile2", "int");
    }

    [Fact]
    public void PartialClass_SendsYieldsInBothFiles_GeneratesAlOverrides()
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

        result.RunResult.GeneratedTrees.Should().HaveCount(1);
        result.RunResult.Diagnostics.Should().BeEmpty();

        var generated = result.RunResult.GeneratedTrees[0];

        // Verify SendsMessage and YieldsOutput from both partials are combined correctly
        generated.Should().RegisterSentMessageType("string")
                      .And.RegisterSentMessageType("int")
                      .And.RegisterYieldedOutputType("string")
                      .And.RegisterYieldedOutputType("string");
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
        result.RunResult.Diagnostics.Should().Contain(d => d.Id == "MAFGENWF003");

        // Should NOT generate any source (to avoid CS0260)
        result.RunResult.GeneratedTrees.Should().BeEmpty(
            "non-partial classes should not have source generated to avoid CS0260 compiler error");
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

        result.RunResult.Diagnostics.Should().Contain(d => d.Id == "MAFGENWF004");
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

        result.RunResult.Diagnostics.Should().Contain(d => d.Id == "MAFGENWF007");
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

        result.RunResult.Diagnostics.Should().Contain(d => d.Id == "MAFGENWF005");
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

        result.RunResult.Diagnostics.Should().Contain(d => d.Id == "MAFGENWF001");
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
        result.RunResult.Diagnostics.Should().Contain(d => d.Id == "MAFGENWF006");
        result.RunResult.GeneratedTrees.Should().BeEmpty();
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

        result.RunResult.GeneratedTrees.Should().BeEmpty();
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

        result.RunResult.GeneratedTrees.Should().HaveCount(1);

        var generated = result.RunResult.GeneratedTrees[0];

        generated.Should().RegisterSentMessageType("global::TestNamespace.MessageA")
                      .And.RegisterSentMessageType("global::TestNamespace.MessageB")
                      .And.RegisterSentMessageType("global::TestNamespace.MessageC");
    }

    [Fact]
    public void ProtocolOnly_NonPartialClass_ProducesDiagnostic()
    {
        var source = """
            using System;
            using System.Threading;
            using System.Threading.Tasks;
            using Microsoft.Agents.AI.Workflows;

            namespace TestNamespace;

            public class BroadcastMessage { }

            [SendsMessage(typeof(BroadcastMessage))]
            public class TestExecutor : Executor
            {
                public TestExecutor() : base("test") { }
            }
            """;

        var result = GeneratorTestHelper.RunGenerator(source);

        // Should produce MAFGENWF003 diagnostic (class must be partial)
        result.RunResult.Diagnostics.Should().Contain(d => d.Id == "MAFGENWF003");
        result.RunResult.GeneratedTrees.Should().BeEmpty();
    }

    [Fact]
    public void ProtocolOnly_NonExecutorClass_ProducesDiagnostic()
    {
        var source = """
            using System;
            using System.Threading;
            using System.Threading.Tasks;
            using Microsoft.Agents.AI.Workflows;

            namespace TestNamespace;

            public class BroadcastMessage { }

            [SendsMessage(typeof(BroadcastMessage))]
            public partial class NotAnExecutor
            {
            }
            """;

        var result = GeneratorTestHelper.RunGenerator(source);

        // Should produce MAFGENWF004 diagnostic (must derive from Executor)
        result.RunResult.Diagnostics.Should().Contain(d => d.Id == "MAFGENWF004");
        result.RunResult.GeneratedTrees.Should().BeEmpty();
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

        result.RunResult.GeneratedTrees.Should().HaveCount(1);
        result.RunResult.Diagnostics.Should().BeEmpty();

        var generated = result.RunResult.GeneratedTrees[0];

        // Verify partial declarations are present
        generated.Should().HaveHierarchy("OuterClass", "TestExecutor")
        // Verify protocol types are generated
                      .And.RegisterSentMessageType("global::TestNamespace.BroadcastMessage");
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

        result.RunResult.GeneratedTrees.Should().HaveCount(1);

        var generated = result.RunResult.GeneratedTrees[0];

        generated.Should().HaveHierarchy("GenericExecutor<T>")
                      .And.RegisterSentMessageType("global::TestNamespace.BroadcastMessage");
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

        result.RunResult.GeneratedTrees.Should().HaveCount(1);

        var generated = result.RunResult.GeneratedTrees[0];

        generated.Should().HaveHierarchy("GenericExecutor<T>")
                      .And.AddHandler("this.HandleMessage", "T");
    }

    #endregion
}
