// Copyright (c) Microsoft. All rights reserved.

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

        var generated = result.RunResult.GeneratedTrees[0].ToString();
        generated.Should().Contain("protected override RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder)");
        generated.Should().Contain(".AddHandler<string>(this.HandleMessage)");
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

        var generated = result.RunResult.GeneratedTrees[0].ToString();
        generated.Should().Contain("protected override ISet<Type> ConfigureYieldTypes()");
        generated.Should().Contain("types.Add(typeof(global::TestNamespace.OutputMessage))");
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

        var generated = result.RunResult.GeneratedTrees[0].ToString();
        generated.Should().Contain("protected override ISet<Type> ConfigureSentTypes()");
        generated.Should().Contain("types.Add(typeof(global::TestNamespace.SendMessage))");
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

        var generated = result.RunResult.GeneratedTrees[0].ToString();
        generated.Should().Contain("protected override ISet<Type> ConfigureSentTypes()");
        generated.Should().Contain("types.Add(typeof(global::TestNamespace.BroadcastMessage))");
    }

    [Fact]
    public void ClassLevel_YieldsMessageAttribute_GeneratesConfigureYieldTypes()
    {
        var source = """
            using System;
            using System.Threading;
            using System.Threading.Tasks;
            using Microsoft.Agents.AI.Workflows;

            namespace TestNamespace;

            public class YieldedMessage { }

            [YieldsMessage(typeof(YieldedMessage))]
            public partial class TestExecutor : Executor
            {
                public TestExecutor() : base("test") { }

                [MessageHandler]
                private void HandleMessage(string message, IWorkflowContext context) { }
            }
            """;

        var result = GeneratorTestHelper.RunGenerator(source);

        result.RunResult.GeneratedTrees.Should().HaveCount(1);

        var generated = result.RunResult.GeneratedTrees[0].ToString();
        generated.Should().Contain("protected override ISet<Type> ConfigureYieldTypes()");
        generated.Should().Contain("types.Add(typeof(global::TestNamespace.YieldedMessage))");
    }

    #endregion

    #region Nested Class Tests

    [Fact]
    public void NestedClass_GeneratesCorrectPartialHierarchy()
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

        var generated = result.RunResult.GeneratedTrees[0].ToString();
        generated.Should().Contain("partial class OuterClass");
        generated.Should().Contain("partial class TestExecutor");
    }

    #endregion

    #region Diagnostic Tests

    [Fact]
    public void NonPartialClass_ProducesDiagnostic()
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

        result.RunResult.Diagnostics.Should().Contain(d => d.Id == "WFGEN003");
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

        result.RunResult.Diagnostics.Should().Contain(d => d.Id == "WFGEN004");
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

        result.RunResult.Diagnostics.Should().Contain(d => d.Id == "WFGEN007");
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

        result.RunResult.Diagnostics.Should().Contain(d => d.Id == "WFGEN005");
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

        result.RunResult.Diagnostics.Should().Contain(d => d.Id == "WFGEN001");
    }

    #endregion

    #region No Generation Tests

    [Fact]
    public void ClassWithManualConfigureRoutes_DoesNotGenerate()
    {
        var source = """
            using System.Threading;
            using System.Threading.Tasks;
            using Microsoft.Agents.AI.Workflows;

            namespace TestNamespace;

            public partial class TestExecutor : Executor
            {
                public TestExecutor() : base("test") { }

                protected override RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder)
                {
                    return routeBuilder;
                }

                [MessageHandler]
                private void HandleMessage(string message, IWorkflowContext context) { }
            }
            """;

        var result = GeneratorTestHelper.RunGenerator(source);

        // Should produce diagnostic but not generate code
        result.RunResult.Diagnostics.Should().Contain(d => d.Id == "WFGEN006");
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

        var generated = result.RunResult.GeneratedTrees[0].ToString();
        generated.Should().Contain("partial class GenericExecutor<T>");
        generated.Should().Contain(".AddHandler<T>(this.HandleMessage)");
    }

    #endregion
}
