// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

/// <summary>
/// Regression tests for polymorphic output type handling in workflows.
/// Verifies that executors can return derived types when the declared output type is a base class.
/// </summary>
/// <remarks>
/// This addresses GitHub issue #4134: InvalidOperationException when returning derived type as workflow output.
/// </remarks>
public partial class PolymorphicOutputTests
{
    #region Test Type Hierarchy

    /// <summary>
    /// Base class used as declared output type.
    /// </summary>
    public class BaseOutput
    {
        public virtual string Name => "BaseOutput";
    }

    /// <summary>
    /// Derived class returned at runtime.
    /// </summary>
    public class DerivedOutput : BaseOutput
    {
        public override string Name => "DerivedOutput";
    }

    /// <summary>
    /// Second-level derived class for testing multiple inheritance levels.
    /// </summary>
    public class GrandchildOutput : DerivedOutput
    {
        public override string Name => "GrandchildOutput";
    }

    /// <summary>
    /// Unrelated class that should NOT be accepted as output.
    /// </summary>
    public class UnrelatedOutput
    {
        public string Name => "UnrelatedOutput";
    }

    #endregion

    #region Test Executors

    /// <summary>
    /// Executor that declares BaseOutput as yield type but returns DerivedOutput.
    /// </summary>
    internal sealed class DerivedOutputExecutor() : Executor(nameof(DerivedOutputExecutor))
    {
        protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder)
        {
            return protocolBuilder.ConfigureRoutes(routeBuilder =>
                routeBuilder.AddHandler<string, BaseOutput>(this.HandleAsync));
        }

        private async ValueTask<BaseOutput> HandleAsync(string input, IWorkflowContext context, CancellationToken cancellationToken)
        {
            await Task.Delay(10, cancellationToken);

            // Arrange: Return a derived type where the method signature declares the base type
            return new DerivedOutput();
        }
    }

    /// <summary>
    /// Executor that declares BaseOutput as yield type but returns GrandchildOutput (two levels deep).
    /// </summary>
    internal sealed class GrandchildOutputExecutor() : Executor(nameof(GrandchildOutputExecutor))
    {
        protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder)
        {
            return protocolBuilder.ConfigureRoutes(routeBuilder =>
                routeBuilder.AddHandler<string, BaseOutput>(this.HandleAsync));
        }

        private async ValueTask<BaseOutput> HandleAsync(string input, IWorkflowContext context, CancellationToken cancellationToken)
        {
            await Task.Delay(10, cancellationToken);

            // Arrange: Return a grandchild type (two inheritance levels)
            return new GrandchildOutput();
        }
    }

    /// <summary>
    /// Executor that attempts to return an unrelated type - should fail validation.
    /// This executor intentionally bypasses type safety to test runtime validation.
    /// </summary>
    internal sealed class UnrelatedOutputExecutor() : Executor(nameof(UnrelatedOutputExecutor))
    {
        protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder)
        {
            return protocolBuilder.ConfigureRoutes(routeBuilder =>
                routeBuilder.AddHandler<string, BaseOutput>(this.HandleAsync));
        }

        private async ValueTask<BaseOutput> HandleAsync(string input, IWorkflowContext context, CancellationToken cancellationToken)
        {
            // Arrange: Attempt to yield an unrelated type - should throw
            UnrelatedOutput unrelated = new();
            await context.YieldOutputAsync(unrelated, cancellationToken).ConfigureAwait(false);

            // This line should not be reached
            return new BaseOutput();
        }
    }

    /// <summary>
    /// Executor that returns the exact declared type (baseline test).
    /// </summary>
    internal sealed class ExactTypeExecutor() : Executor(nameof(ExactTypeExecutor))
    {
        protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder)
        {
            return protocolBuilder.ConfigureRoutes(routeBuilder =>
                routeBuilder.AddHandler<string, BaseOutput>(this.HandleAsync));
        }

        private ValueTask<BaseOutput> HandleAsync(string input, IWorkflowContext context, CancellationToken cancellationToken)
        {
            BaseOutput result = new();
            return new ValueTask<BaseOutput>(result);
        }
    }

    #endregion

    #region Tests

    /// <summary>
    /// Verifies that returning a derived type when the declared output type is a base class succeeds.
    /// This is the main regression test for GitHub issue #4134.
    /// </summary>
    [Fact]
    public async Task ReturningDerivedType_WhenBaseTypeIsDeclared_ShouldSucceedAsync()
    {
        // Arrange
        DerivedOutputExecutor executor = new();
        WorkflowBuilder builder = new WorkflowBuilder(executor).WithOutputFrom(executor);
        Workflow workflow = builder.Build();

        // Act
        List<WorkflowEvent> events = [];
        await using StreamingRun run = await InProcessExecution.RunStreamingAsync(workflow, "test input");
        await foreach (WorkflowEvent evt in run.WatchStreamAsync())
        {
            events.Add(evt);
        }

        // Assert
        Assert.NotEmpty(events);

        List<WorkflowOutputEvent> outputEvents = events.OfType<WorkflowOutputEvent>().ToList();
        Assert.Single(outputEvents);

        WorkflowOutputEvent outputEvent = outputEvents.Single();
        DerivedOutput derivedOutput = Assert.IsType<DerivedOutput>(outputEvent.Data);
        Assert.Equal("DerivedOutput", derivedOutput.Name);

        // Verify no error events
        List<WorkflowErrorEvent> errorEvents = events.OfType<WorkflowErrorEvent>().ToList();
        Assert.Empty(errorEvents ?? []);
    }

    /// <summary>
    /// Verifies that returning a grandchild type (multiple inheritance levels) succeeds.
    /// </summary>
    [Fact]
    public async Task ReturningGrandchildType_WhenBaseTypeIsDeclared_ShouldSucceedAsync()
    {
        // Arrange
        GrandchildOutputExecutor executor = new();
        WorkflowBuilder builder = new WorkflowBuilder(executor).WithOutputFrom(executor);
        Workflow workflow = builder.Build();

        // Act
        List<WorkflowEvent> events = [];
        await using StreamingRun run = await InProcessExecution.RunStreamingAsync(workflow, "test input");
        await foreach (WorkflowEvent evt in run.WatchStreamAsync())
        {
            events.Add(evt);
        }

        // Assert
        Assert.NotEmpty(events);

        List<WorkflowOutputEvent> outputEvents = events.OfType<WorkflowOutputEvent>().ToList();
        Assert.Single(outputEvents);

        WorkflowOutputEvent outputEvent = outputEvents.Single();
        GrandchildOutput grandchildOutput = Assert.IsType<GrandchildOutput>(outputEvent.Data);
        Assert.Equal("GrandchildOutput", grandchildOutput.Name);

        // Verify no error events
        List<WorkflowErrorEvent> errorEvents = events.OfType<WorkflowErrorEvent>().ToList();
        Assert.Empty(errorEvents ?? []);
    }

    /// <summary>
    /// Verifies that returning an unrelated type still throws InvalidOperationException.
    /// This ensures the fix doesn't break the existing validation for truly incompatible types.
    /// </summary>
    [Fact]
    public async Task ReturningUnrelatedType_WhenBaseTypeIsDeclared_ShouldFailAsync()
    {
        // Arrange
        UnrelatedOutputExecutor executor = new();
        WorkflowBuilder builder = new WorkflowBuilder(executor).WithOutputFrom(executor);
        Workflow workflow = builder.Build();

        // Act
        List<WorkflowEvent> events = [];
        await using StreamingRun run = await InProcessExecution.RunStreamingAsync(workflow, "test input");
        await foreach (WorkflowEvent evt in run.WatchStreamAsync())
        {
            events.Add(evt);
        }

        // Assert: Should have an error event with InvalidOperationException message
        List<WorkflowErrorEvent> errorEvents = events.OfType<WorkflowErrorEvent>().ToList();
        Assert.Single(errorEvents);

        WorkflowErrorEvent errorEvent = errorEvents.Single();
        string errorMessage = errorEvent.Data?.ToString() ?? string.Empty;
        Assert.Contains("Cannot output object of type UnrelatedOutput", errorMessage);
        Assert.Contains("BaseOutput", errorMessage);
    }

    /// <summary>
    /// Verifies that returning the exact declared type still works (baseline test).
    /// </summary>
    [Fact]
    public async Task ReturningExactType_WhenSameTypeIsDeclared_ShouldSucceedAsync()
    {
        // Arrange: Create an executor that returns the exact declared type
        ExactTypeExecutor executor = new();
        WorkflowBuilder builder = new WorkflowBuilder(executor).WithOutputFrom(executor);
        Workflow workflow = builder.Build();

        // Act
        List<WorkflowEvent> events = [];
        await using StreamingRun run = await InProcessExecution.RunStreamingAsync(workflow, "test input");
        await foreach (WorkflowEvent evt in run.WatchStreamAsync())
        {
            events.Add(evt);
        }

        // Assert
        Assert.NotEmpty(events);

        List<WorkflowOutputEvent> outputEvents = events.OfType<WorkflowOutputEvent>().ToList();
        Assert.Single(outputEvents);

        WorkflowOutputEvent outputEvent = outputEvents.Single();
        Assert.IsType<BaseOutput>(outputEvent.Data);

        // Verify no error events
        List<WorkflowErrorEvent> errorEvents = events.OfType<WorkflowErrorEvent>().ToList();
        Assert.Empty(errorEvents ?? []);
    }

    #endregion
}
