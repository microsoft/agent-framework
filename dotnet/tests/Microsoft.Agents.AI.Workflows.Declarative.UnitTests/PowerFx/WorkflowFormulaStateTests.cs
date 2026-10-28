// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Checkpointing;
using Microsoft.Agents.AI.Workflows.Declarative.Interpreter;
using Microsoft.Agents.AI.Workflows.Declarative.Kit;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Agents.ObjectModel;
using Microsoft.Agents.ObjectModel.Abstractions;
using Microsoft.PowerFx.Types;
using Moq;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.PowerFx;

public class WorkflowFormulaStateTests
{
    internal WorkflowFormulaState State { get; } = new(RecalcEngineFactory.Create());

    [Fact]
    public void GetWithImplicitScope()
    {
        // Arrange
        FormulaValue testValue = FormulaValue.New("test");
        this.State.Set("key1", testValue);

        // Act
        FormulaValue result = this.State.Get("key1");

        // Assert
        Assert.Equal(testValue, result);
    }

    [Fact]
    public void GetWithSpecifiedScope()
    {
        // Arrange
        FormulaValue testValue = FormulaValue.New("test");
        this.State.Set("key1", testValue, VariableScopeNames.Global);

        // Act
        FormulaValue result = this.State.Get("key1", VariableScopeNames.Global);

        // Assert
        Assert.Equal(testValue, result);
    }

    [Fact]
    public void SetDefaultScope()
    {
        // Arrange
        FormulaValue testValue = FormulaValue.New("test");

        // Act
        this.State.Set("key1", testValue);

        // Assert
        FormulaValue result = this.State.Get("key1");
        Assert.Equal(testValue, result);
    }

    [Fact]
    public void SetSpecifiedScope()
    {
        // Arrange
        FormulaValue testValue = FormulaValue.New("test");

        // Act
        this.State.Set("key1", testValue, VariableScopeNames.System);

        // Assert
        FormulaValue result = this.State.Get("key1", VariableScopeNames.System);
        Assert.Equal(testValue, result);
    }

    [Fact]
    public void SetOverwritesExistingValue()
    {
        // Arrange
        FormulaValue initialValue = FormulaValue.New("initial");
        FormulaValue newValue = FormulaValue.New("new");

        // Act
        this.State.Set("key1", initialValue);
        this.State.Set("key1", newValue);

        // Assert
        FormulaValue result = this.State.Get("key1");
        Assert.Equal(newValue, result);
    }

    [Theory]
    [InlineData("item", "ITEM", false)]
    [InlineData("ITEM", "item", false)]
    [InlineData("item", "ITEM", true)]
    [InlineData("ITEM", "item", true)]
    public void SetKeepsCaseVariantVariablesIndependent(string firstName, string secondName, bool useBlank)
    {
        // Arrange
        FormulaValue firstValue = FormulaValue.New("first");
        FormulaValue secondValue = useBlank ? FormulaValue.NewBlank() : FormulaValue.New("second");
        this.State.Set(firstName, firstValue, sensitivity: SensitivityLevel.Sensitive);

        // Act
        this.State.Set(secondName, secondValue);
        this.State.Bind();
        EvaluationResult<string> firstResult = this.State.Evaluator.GetValue(StringExpression.Expression($"Local.{firstName}"));
        EvaluationResult<string> secondResult = this.State.Evaluator.GetValue(StringExpression.Expression($"Local.{secondName}"));

        // Assert
        Assert.Equal(firstValue, this.State.Get(firstName));
        Assert.Equal(secondValue, this.State.Get(secondName));
        Assert.Equal("first", firstResult.Value);
        Assert.Equal(useBlank ? string.Empty : "second", secondResult.Value);
        Assert.Equal(SensitivityLevel.Sensitive, firstResult.Sensitivity);
        Assert.Equal(SensitivityLevel.None, secondResult.Sensitivity);
    }

    [Theory]
    [InlineData("item", "ITEM")]
    [InlineData("ITEM", "item")]
    public void SetSensitivityKeepsCaseVariantVariablesIndependent(string firstName, string secondName)
    {
        // Arrange
        this.State.Set(firstName, FormulaValue.New("first"), sensitivity: SensitivityLevel.Sensitive);
        this.State.Set(secondName, FormulaValue.New("second"), sensitivity: SensitivityLevel.Sensitive);

        // Act
        this.State.SetSensitivity(secondName, VariableScopeNames.Local, SensitivityLevel.None);

        // Assert
        Assert.Equal("first", Assert.IsType<StringValue>(this.State.Get(firstName)).Value);
        Assert.Equal("second", Assert.IsType<StringValue>(this.State.Get(secondName)).Value);
        Assert.Equal(SensitivityLevel.Sensitive, this.State.GetSensitivity(firstName));
        Assert.Equal(SensitivityLevel.None, this.State.GetSensitivity(secondName));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task RestoreAsync_KeepsCaseVariantVariablesIndependentAsync(bool reverseOrder)
    {
        // Arrange
        Mock<IWorkflowContext> context = new(MockBehavior.Strict);
        HashSet<string> keys = reverseOrder ? ["ITEM", "item"] : ["item", "ITEM"];
        context.Setup(c => c.ReadStateKeysAsync(It.IsAny<string?>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync((string? scopeName, CancellationToken _) => string.Equals(scopeName, VariableScopeNames.Local, StringComparison.Ordinal) ? keys : []);
        context.Setup(c => c.ReadStateAsync<PortableValue>("item", VariableScopeNames.Local, It.IsAny<CancellationToken>()))
            .ReturnsAsync(new PortableValue("first"));
        context.Setup(c => c.ReadStateAsync<PortableValue>("ITEM", VariableScopeNames.Local, It.IsAny<CancellationToken>()))
            .ReturnsAsync(new PortableValue("second"));
        string sensitivityScope = WorkflowFormulaState.GetSensitivityScopeName(VariableScopeNames.Local);
        context.Setup(c => c.ReadStateAsync<SensitivityLevel>("item", sensitivityScope, It.IsAny<CancellationToken>()))
            .ReturnsAsync(SensitivityLevel.Sensitive);
        context.Setup(c => c.ReadStateAsync<SensitivityLevel>("ITEM", sensitivityScope, It.IsAny<CancellationToken>()))
            .ReturnsAsync(SensitivityLevel.None);

        // Act
        await this.State.RestoreAsync(context.Object, CancellationToken.None);

        // Assert
        Assert.Equal("first", Assert.IsType<StringValue>(this.State.Get("item")).Value);
        Assert.Equal("second", Assert.IsType<StringValue>(this.State.Get("ITEM")).Value);
        Assert.Equal(SensitivityLevel.Sensitive, this.State.GetSensitivity("item"));
        Assert.Equal(SensitivityLevel.None, this.State.GetSensitivity("ITEM"));
    }

    [Fact]
    public async Task RestoreAsync_RestoresPersistedSensitivityAsync()
    {
        // Arrange
        Mock<IWorkflowContext> context = new(MockBehavior.Strict);
        context.Setup(c => c.ReadStateKeysAsync(It.IsAny<string?>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync((string? scopeName, CancellationToken _) => scopeName == VariableScopeNames.Local ? new HashSet<string> { "secret" } : []);
        context.Setup(c => c.ReadStateAsync<PortableValue>("secret", VariableScopeNames.Local, It.IsAny<CancellationToken>()))
            .ReturnsAsync(new PortableValue("secret-value"));
        context.Setup(c => c.ReadStateAsync<SensitivityLevel>("secret", WorkflowFormulaState.GetSensitivityScopeName(VariableScopeNames.Local), It.IsAny<CancellationToken>()))
            .ReturnsAsync(SensitivityLevel.Sensitive);

        // Act
        await this.State.RestoreAsync(context.Object, CancellationToken.None);

        // Assert
        Assert.Equal(SensitivityLevel.Sensitive, this.State.GetSensitivity("secret"));
    }

    [Theory]
    [InlineData(VariableScopeNames.Local, VariableScopeNames.Topic, false, false)]
    [InlineData(VariableScopeNames.Topic, VariableScopeNames.Local, false, false)]
    [InlineData(VariableScopeNames.Local, VariableScopeNames.Topic, true, false)]
    [InlineData(VariableScopeNames.Topic, VariableScopeNames.Local, true, false)]
    [InlineData(VariableScopeNames.Local, VariableScopeNames.Topic, false, true)]
    [InlineData(VariableScopeNames.Topic, VariableScopeNames.Local, false, true)]
    public async Task RestoreAsync_PreservesLatestAliasAssignmentAsync(string firstScope, string secondScope, bool sensitive, bool clear)
    {
        // Arrange
        Dictionary<(string? Scope, string Key), PortableValue> values = [];
        Dictionary<(string? Scope, string Key), SensitivityLevel> sensitivities = [];
        Mock<IWorkflowContext> source = CreateStateContext(values, sensitivities);
        DeclarativeWorkflowContext context = new(source.Object, this.State);
        await context.QueueStateUpdateAsync("TestValue", FormulaValue.New("first"), firstScope, SensitivityLevel.Sensitive);
        if (clear)
        {
            await context.QueueClearScopeAsync(secondScope);
        }
        else
        {
            await context.QueueStateUpdateAsync("TestValue", "second", secondScope, sensitive ? SensitivityLevel.Sensitive : SensitivityLevel.None);
        }
        object? expectedValue = this.State.Get("TestValue").ToObject();
        SensitivityLevel expectedSensitivity = this.State.GetSensitivity("TestValue");

        // Act
        WorkflowFormulaState restored = new(RecalcEngineFactory.Create());
        await restored.RestoreAsync(source.Object, CancellationToken.None);

        // Assert
        Assert.Equal(clear ? null : "second", expectedValue);
        Assert.Equal(sensitive ? SensitivityLevel.Sensitive : SensitivityLevel.None, expectedSensitivity);
        Assert.Equal(expectedValue, restored.Get("TestValue", VariableScopeNames.Local).ToObject());
        Assert.Equal(expectedValue, restored.Get("TestValue", VariableScopeNames.Topic).ToObject());
        Assert.Equal(expectedSensitivity, restored.GetSensitivity("TestValue", VariableScopeNames.Local));
        Assert.Equal(expectedSensitivity, restored.GetSensitivity("TestValue", VariableScopeNames.Topic));
    }

    [Theory]
    [InlineData(false, false)]
    [InlineData(true, false)]
    [InlineData(false, true)]
    public async Task RestoreAsync_MigratesLegacyTopicStateAsync(bool sensitive, bool clear)
    {
        // Arrange
        string sensitivityScope = WorkflowFormulaState.GetSensitivityScopeName(VariableScopeNames.Local);
        SensitivityLevel sensitivity = sensitive ? SensitivityLevel.Sensitive : SensitivityLevel.None;
        Dictionary<(string? Scope, string Key), PortableValue> values = new()
        {
            [(VariableScopeNames.Local, "OtherValue")] = new("other"),
            [(VariableScopeNames.Topic, "TestValue")] = new(clear ? UnassignedValue.Instance : "legacy"),
        };
        Dictionary<(string? Scope, string Key), SensitivityLevel> sensitivities = new()
        {
            [(sensitivityScope, "TestValue")] = sensitivity,
        };
        Mock<IWorkflowContext> source = CreateStateContext(values, sensitivities);
        DeclarativeWorkflowContext context = new(source.Object, this.State);

        // Act
        await this.State.RestoreAsync(source.Object, CancellationToken.None);

        // Assert
        Assert.Equal(clear ? null : "legacy", this.State.Get("TestValue").ToObject());
        Assert.Equal(sensitivity, this.State.GetSensitivity("TestValue"));
        Assert.Equal("other", this.State.Get("OtherValue").ToObject());
        Assert.DoesNotContain(values.Keys, key => string.Equals(key.Scope, VariableScopeNames.Topic, StringComparison.Ordinal));
        Assert.Contains((VariableScopeNames.Local, "TestValue"), values.Keys);
        Assert.Equal(sensitivity, sensitivities[(sensitivityScope, "TestValue")]);
        if (!clear)
        {
            Assert.Equal("legacy", await context.ReadStateAsync<string>("TestValue", VariableScopeNames.Topic));
            Assert.Equal("legacy", await context.ReadOrInitStateAsync("TestValue", () => "replacement", VariableScopeNames.Topic));
        }

        await context.QueueClearScopeAsync(VariableScopeNames.Topic);
        await this.State.RestoreCheckpointAsync(source.Object, CancellationToken.None);
        Assert.IsType<BlankValue>(this.State.Get("TestValue"));
        Assert.Equal(SensitivityLevel.None, this.State.GetSensitivity("TestValue"));
    }

    [Fact]
    public async Task RestoreAsync_RejectsConflictingAliasEntriesOnEveryAttemptAsync()
    {
        // Arrange
        Dictionary<(string? Scope, string Key), PortableValue> values = new()
        {
            [(VariableScopeNames.Topic, "OtherValue")] = new("other"),
            [(VariableScopeNames.Local, "TestValue")] = new("first"),
            [(VariableScopeNames.Topic, "TestValue")] = new("second"),
        };
        Dictionary<(string? Scope, string Key), SensitivityLevel> sensitivities = new()
        {
            [(WorkflowFormulaState.GetSensitivityScopeName(VariableScopeNames.Local), "TestValue")] = SensitivityLevel.None,
        };
        Mock<IWorkflowContext> source = CreateStateContext(values, sensitivities);

        // Act
        DeclarativeActionException first = await Assert.ThrowsAsync<DeclarativeActionException>(
            async () => await this.State.RestoreAsync(source.Object, CancellationToken.None));
        DeclarativeActionException retry = await Assert.ThrowsAsync<DeclarativeActionException>(
            async () => await this.State.RestoreAsync(source.Object, CancellationToken.None));

        // Assert
        Assert.Contains("conflicting", first.Message);
        Assert.Equal(first.Message, retry.Message);
        Assert.Equal(3, values.Count);
        Assert.Equal(SensitivityLevel.None, Assert.Single(sensitivities).Value);
        source.Verify(c => c.QueueStateUpdateAsync(It.IsAny<string>(), It.IsAny<object>(), It.IsAny<string?>(), It.IsAny<CancellationToken>()), Times.Never);
        source.Verify(c => c.QueueClearScopeAsync(It.IsAny<string?>(), It.IsAny<CancellationToken>()), Times.Never);
    }

    [Theory]
    [InlineData(42)]
    [InlineData(42L)]
    [InlineData(1.5f)]
    [InlineData(1.5d)]
    public async Task RestoreAsync_LegacyMigrationPreservesNativeTypesAsync(object value)
    {
        // Arrange
        Dictionary<(string? Scope, string Key), PortableValue> values = new()
        {
            [(VariableScopeNames.Topic, "TestValue")] = new(value),
        };
        Mock<IWorkflowContext> source = CreateStateContext(values, new()
        {
            [(WorkflowFormulaState.GetSensitivityScopeName(VariableScopeNames.Local), "TestValue")] = SensitivityLevel.None,
        });

        // Act
        await this.State.RestoreAsync(source.Object, CancellationToken.None);

        // Assert
        PortableValue migrated = values[(VariableScopeNames.Local, "TestValue")];
        Assert.True(migrated.TypeId.IsMatch(value.GetType()));
        Assert.Equal(value, migrated.AsType(value.GetType()));
    }

    [Theory]
    [InlineData(false, false)]
    [InlineData(false, true)]
    [InlineData(true, false)]
    [InlineData(true, true)]
    public async Task ResumeAsync_PublishesLegacyMigrationBeforeNextExecutorAsync(bool offThread, bool clear)
    {
        // Arrange
        StateExecutor source = new("source", SeedLegacyStateAsync, this.State);
        StateExecutor writer = new("writer", async (context, cancellationToken) =>
        {
            DeclarativeWorkflowContext declarative = new(context, this.State);
            if (clear)
            {
                await declarative.QueueClearScopeAsync(VariableScopeNames.Topic, cancellationToken);
            }
            else
            {
                await declarative.QueueStateUpdateAsync("TestValue", "updated", VariableScopeNames.Topic, cancellationToken);
            }
        });
        Workflow workflow = new WorkflowBuilder(source).AddEdge(source, writer).Build();
        CheckpointManager checkpoints = CheckpointManager.CreateInMemory();
        var environment = (offThread ? InProcessExecution.OffThread : InProcessExecution.Lockstep).WithCheckpointing(checkpoints);
        CheckpointInfo? legacyCheckpoint = null;
        await using (StreamingRun run = await environment.RunStreamingAsync(workflow, 1))
        {
            await foreach (WorkflowEvent evt in run.WatchStreamAsync())
            {
                if (evt is SuperStepCompletedEvent { CompletionInfo.Checkpoint: { } saved })
                {
                    legacyCheckpoint ??= saved;
                }
            }
        }
        Assert.NotNull(legacyCheckpoint);

        // Act
        CheckpointInfo? updatedCheckpoint = null;
        await using StreamingRun resumed = await environment.ResumeStreamingAsync(workflow, legacyCheckpoint);
        await foreach (WorkflowEvent evt in resumed.WatchStreamAsync())
        {
            Assert.False(evt is WorkflowErrorEvent, (evt as WorkflowErrorEvent)?.Exception?.ToString());
            if (evt is SuperStepCompletedEvent { CompletionInfo.Checkpoint: { } saved })
            {
                updatedCheckpoint = saved;
            }
        }
        Assert.NotNull(updatedCheckpoint);
        await resumed.RestoreCheckpointAsync(updatedCheckpoint);

        // Assert
        Assert.Equal(clear ? null : "updated", this.State.Get("TestValue").ToObject());
        Assert.Equal(SensitivityLevel.None, this.State.GetSensitivity("TestValue"));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task ResumeAsync_PublishesLegacyMigrationBeforePostLoadHooksAsync(bool offThread)
    {
        // Arrange
        StateExecutor source = new("source", SeedLegacyStateAsync, this.State);
        bool hookInvoked = false;
        StateExecutor reader = new("reader", (_, _) => default, restored: async (context, cancellationToken) =>
        {
            Assert.Equal("legacy", await context.ReadStateAsync<string>("TestValue", VariableScopeNames.Local, cancellationToken));
            Assert.Equal(SensitivityLevel.Sensitive, await context.ReadStateAsync<SensitivityLevel>(
                "TestValue", WorkflowFormulaState.GetSensitivityScopeName(VariableScopeNames.Local), cancellationToken));
            Assert.Empty(await context.ReadStateKeysAsync(VariableScopeNames.Topic, cancellationToken));
            hookInvoked = true;
        });
        Workflow workflow = new WorkflowBuilder(source).AddEdge(source, reader).Build();
        CheckpointManager checkpoints = CheckpointManager.CreateInMemory();
        var environment = (offThread ? InProcessExecution.OffThread : InProcessExecution.Lockstep).WithCheckpointing(checkpoints);
        CheckpointInfo? legacyCheckpoint = null;
        await using (StreamingRun run = await environment.RunStreamingAsync(workflow, 1))
        {
            await foreach (WorkflowEvent evt in run.WatchStreamAsync())
            {
                if (evt is SuperStepCompletedEvent { CompletionInfo.Checkpoint: { } saved })
                {
                    legacyCheckpoint ??= saved;
                }
            }
        }
        Assert.NotNull(legacyCheckpoint);

        // Act
        await using StreamingRun resumed = await environment.ResumeStreamingAsync(workflow, legacyCheckpoint);
        await resumed.RestoreCheckpointAsync(legacyCheckpoint);
        await resumed.RestoreCheckpointAsync(legacyCheckpoint);

        // Assert
        Assert.True(hookInvoked);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task ResumeAsync_PreservesUnmarkedTopicEntriesAsync(bool offThread)
    {
        // Arrange
        StateExecutor source = new("source", async (context, cancellationToken) =>
        {
            await SeedLegacyStateAsync(context, cancellationToken);
            await context.QueueStateUpdateAsync("NativeValue", 42, VariableScopeNames.Topic, cancellationToken);
            await context.QueueStateUpdateAsync("NativeValue", 7, VariableScopeNames.Local, cancellationToken);
        }, this.State);
        bool hookInvoked = false;
        StateExecutor reader = new("reader", (_, _) => default, restored: async (context, cancellationToken) =>
        {
            Assert.Equal(42, await context.ReadStateAsync<int>("NativeValue", VariableScopeNames.Topic, cancellationToken));
            Assert.Equal(7, await context.ReadStateAsync<int>("NativeValue", VariableScopeNames.Local, cancellationToken));
            Assert.Equal("legacy", await context.ReadStateAsync<string>("TestValue", VariableScopeNames.Local, cancellationToken));
            Assert.Equal("NativeValue", Assert.Single(await context.ReadStateKeysAsync(VariableScopeNames.Topic, cancellationToken)));
            hookInvoked = true;
        });
        Workflow workflow = new WorkflowBuilder(source).AddEdge(source, reader).Build();
        CheckpointManager checkpoints = CheckpointManager.CreateInMemory();
        var environment = (offThread ? InProcessExecution.OffThread : InProcessExecution.Lockstep).WithCheckpointing(checkpoints);
        CheckpointInfo? legacyCheckpoint = null;
        await using (StreamingRun run = await environment.RunStreamingAsync(workflow, 1))
        {
            await foreach (WorkflowEvent evt in run.WatchStreamAsync())
            {
                if (evt is SuperStepCompletedEvent { CompletionInfo.Checkpoint: { } saved })
                {
                    legacyCheckpoint ??= saved;
                }
            }
        }
        Assert.NotNull(legacyCheckpoint);

        // Act
        await using StreamingRun resumed = await environment.ResumeStreamingAsync(workflow, legacyCheckpoint);

        // Assert
        Assert.True(hookInvoked);
    }

    [Theory]
    [InlineData(false, false)]
    [InlineData(false, true)]
    [InlineData(true, false)]
    [InlineData(true, true)]
    public async Task ResumeAsync_PlainSensitivityAliasesRemainConsistentAsync(bool offThread, bool overwrite)
    {
        // Arrange
        bool resuming = false;
        StateExecutor source = new("source", (context, cancellationToken) =>
            context.QueueStateUpdateWithSensitivityAsync("TestValue",
                new EvaluationResult<string>("initial", SensitivityLevel.Sensitive), VariableScopeNames.Topic, cancellationToken), this.State);
        string expected = overwrite ? "updated" : "initial";
        SensitivityLevel expectedSensitivity = overwrite ? SensitivityLevel.None : SensitivityLevel.Sensitive;
        StateExecutor writer = new("writer", async (context, cancellationToken) =>
        {
            if (!resuming)
            {
                return;
            }
            if (overwrite)
            {
                await context.QueueStateUpdateWithSensitivityAsync("TestValue",
                    new EvaluationResult<string>("updated", SensitivityLevel.None), VariableScopeNames.Topic, cancellationToken);
            }
            EvaluationResult<string?> result = await context.ReadStateWithSensitivityAsync<string>("TestValue", VariableScopeNames.Topic, cancellationToken);
            Assert.Equal(expected, result.Value);
            Assert.Equal(expectedSensitivity, result.Sensitivity);
        });
        Workflow workflow = new WorkflowBuilder(source).AddEdge(source, writer).Build();
        CheckpointManager checkpoints = CheckpointManager.CreateInMemory();
        var environment = (offThread ? InProcessExecution.OffThread : InProcessExecution.Lockstep).WithCheckpointing(checkpoints);
        CheckpointInfo? checkpoint = null;
        await using (StreamingRun run = await environment.RunStreamingAsync(workflow, 1))
        {
            await foreach (WorkflowEvent evt in run.WatchStreamAsync())
            {
                Assert.False(evt is WorkflowErrorEvent, (evt as WorkflowErrorEvent)?.Exception?.ToString());
                if (evt is SuperStepCompletedEvent { CompletionInfo.Checkpoint: { } saved })
                {
                    checkpoint ??= saved;
                }
            }
        }
        Assert.NotNull(checkpoint);

        // Act
        resuming = true;
        CheckpointInfo? updatedCheckpoint = null;
        await using StreamingRun resumed = await environment.ResumeStreamingAsync(workflow, checkpoint);
        await foreach (WorkflowEvent evt in resumed.WatchStreamAsync())
        {
            Assert.False(evt is WorkflowErrorEvent, (evt as WorkflowErrorEvent)?.Exception?.ToString());
            if (evt is SuperStepCompletedEvent { CompletionInfo.Checkpoint: { } saved })
            {
                updatedCheckpoint = saved;
            }
        }
        Assert.NotNull(updatedCheckpoint);
        await resumed.RestoreCheckpointAsync(updatedCheckpoint);

        // Assert
        Assert.Equal(expected, this.State.Get("TestValue").ToObject());
        Assert.Equal(expectedSensitivity, this.State.GetSensitivity("TestValue"));
    }

    [Theory]
    [InlineData(false, false)]
    [InlineData(false, true)]
    [InlineData(true, false)]
    [InlineData(true, true)]
    public async Task EvaluateAsync_PlainSensitivityAliasesRemainConsistentAsync(bool offThread, bool overwrite)
    {
        // Arrange
        StateExecutor source = new("source", async (context, cancellationToken) =>
        {
            await context.QueueStateUpdateWithSensitivityAsync("TestValue",
                new EvaluationResult<string>("initial", SensitivityLevel.Sensitive), VariableScopeNames.Topic, cancellationToken);
            EvaluationResult<string?> initial = await context.EvaluateValueWithSensitivityAsync<string>("Local.TestValue", cancellationToken);
            Assert.Equal("initial", initial.Value);
            Assert.Equal(SensitivityLevel.Sensitive, initial.Sensitivity);
            if (overwrite)
            {
                await context.QueueStateUpdateWithSensitivityAsync("TestValue",
                    new EvaluationResult<string>("updated", SensitivityLevel.None), VariableScopeNames.Topic, cancellationToken);
            }

            EvaluationResult<string?> read = await context.ReadStateWithSensitivityAsync<string>("TestValue", VariableScopeNames.Topic, cancellationToken);
            EvaluationResult<string?> evaluated = await context.EvaluateValueWithSensitivityAsync<string>("Local.TestValue", cancellationToken);

            // Assert
            Assert.Equal(overwrite ? "updated" : "initial", read.Value);
            Assert.Equal(overwrite ? SensitivityLevel.None : SensitivityLevel.Sensitive, read.Sensitivity);
            Assert.Equal(read.Value, evaluated.Value);
            Assert.Equal(read.Sensitivity, evaluated.Sensitivity);
        });
        Workflow workflow = new WorkflowBuilder(source).Build();
        var environment = offThread ? InProcessExecution.OffThread : InProcessExecution.Lockstep;

        // Act
        await using StreamingRun run = await environment.RunStreamingAsync(workflow, 1);
        await foreach (WorkflowEvent evt in run.WatchStreamAsync())
        {
            Assert.False(evt is WorkflowErrorEvent, (evt as WorkflowErrorEvent)?.Exception?.ToString());
        }
    }

    [Theory]
    [InlineData(false, false, SensitivityLevel.None)]
    [InlineData(false, false, SensitivityLevel.Sensitive)]
    [InlineData(false, true, SensitivityLevel.None)]
    [InlineData(false, true, SensitivityLevel.Sensitive)]
    [InlineData(true, false, SensitivityLevel.None)]
    [InlineData(true, false, SensitivityLevel.Sensitive)]
    [InlineData(true, true, SensitivityLevel.None)]
    [InlineData(true, true, SensitivityLevel.Sensitive)]
    public async Task ResumeAsync_PlainLegacyHelpersWorkWithoutFormulaCallbacksAsync(bool offThread, bool overwrite, SensitivityLevel sensitivity)
    {
        // Arrange
        bool resuming = false;
        IWorkflowContext? resumedContext = null;
        string expected = overwrite ? "updated" : "legacy";
        SensitivityLevel expectedSensitivity = overwrite
            ? sensitivity == SensitivityLevel.Sensitive ? SensitivityLevel.None : SensitivityLevel.Sensitive
            : sensitivity;
        StateExecutor source = new("source", async (context, cancellationToken) =>
        {
            await context.QueueStateUpdateAsync("TestValue", "legacy", VariableScopeNames.Topic, cancellationToken);
            await context.QueueStateUpdateAsync("TestValue", sensitivity,
                WorkflowFormulaState.GetSensitivityScopeName(VariableScopeNames.Local), cancellationToken);
            await context.QueueStateUpdateAsync("OtherValue", "untouched", VariableScopeNames.Topic, cancellationToken);
            await context.QueueStateUpdateAsync("OtherValue", SensitivityLevel.None,
                WorkflowFormulaState.GetSensitivityScopeName(VariableScopeNames.Local), cancellationToken);
            await context.QueueStateUpdateAsync("NativeValue", 42, VariableScopeNames.Topic, cancellationToken);
        });
        StateExecutor writer = new("writer", async (context, cancellationToken) =>
        {
            if (!resuming)
            {
                return;
            }
            resumedContext = context;
            if (overwrite)
            {
                await context.QueueStateUpdateWithSensitivityAsync("TestValue",
                    new EvaluationResult<string>("updated", expectedSensitivity), VariableScopeNames.Topic, cancellationToken);
            }
            foreach (string? scope in new string?[] { null, VariableScopeNames.Local, VariableScopeNames.Topic })
            {
                EvaluationResult<string?> result = await context.ReadStateWithSensitivityAsync<string>("TestValue", scope, cancellationToken);
                Assert.Equal(expected, result.Value);
                Assert.Equal(expectedSensitivity, result.Sensitivity);
            }
            if (!overwrite)
            {
                Assert.Equal("legacy", await context.ReadStateAsync<string>("TestValue", VariableScopeNames.Topic, cancellationToken));
                Assert.DoesNotContain("TestValue", await context.ReadStateKeysAsync(VariableScopeNames.Local, cancellationToken));
            }
            Assert.Equal("untouched", await context.ReadStateAsync<string>("OtherValue", VariableScopeNames.Topic, cancellationToken));
            Assert.DoesNotContain("OtherValue", await context.ReadStateKeysAsync(VariableScopeNames.Local, cancellationToken));
            EvaluationResult<string?> evaluated = await context.EvaluateValueWithSensitivityAsync<string>("Local.TestValue", cancellationToken);
            Assert.Equal(expected, evaluated.Value);
            Assert.Equal(expectedSensitivity, evaluated.Sensitivity);
        });
        Workflow workflow = new WorkflowBuilder(source).AddEdge(source, writer).Build();
        CheckpointManager checkpoints = CheckpointManager.CreateInMemory();
        var environment = (offThread ? InProcessExecution.OffThread : InProcessExecution.Lockstep).WithCheckpointing(checkpoints);
        CheckpointInfo? checkpoint = null;
        await using (StreamingRun run = await environment.RunStreamingAsync(workflow, 1))
        {
            await foreach (WorkflowEvent evt in run.WatchStreamAsync())
            {
                Assert.False(evt is WorkflowErrorEvent, (evt as WorkflowErrorEvent)?.Exception?.ToString());
                if (evt is SuperStepCompletedEvent { CompletionInfo.Checkpoint: { } saved })
                {
                    checkpoint ??= saved;
                }
            }
        }
        Assert.NotNull(checkpoint);

        // Act
        resuming = true;
        CheckpointInfo? updatedCheckpoint = null;
        await using StreamingRun resumed = await environment.ResumeStreamingAsync(workflow, checkpoint);
        await foreach (WorkflowEvent evt in resumed.WatchStreamAsync())
        {
            Assert.False(evt is WorkflowErrorEvent, (evt as WorkflowErrorEvent)?.Exception?.ToString());
            if (evt is SuperStepCompletedEvent { CompletionInfo.Checkpoint: { } saved })
            {
                updatedCheckpoint = saved;
            }
        }
        Assert.NotNull(updatedCheckpoint);
        await resumed.RestoreCheckpointAsync(updatedCheckpoint);

        // Assert
        Assert.NotNull(resumedContext);
        EvaluationResult<string?> restored = await resumedContext.ReadStateWithSensitivityAsync<string>("TestValue", VariableScopeNames.Topic);
        Assert.Equal(expected, restored.Value);
        Assert.Equal(expectedSensitivity, restored.Sensitivity);
        if (overwrite)
        {
            Assert.DoesNotContain("TestValue", await resumedContext.ReadStateKeysAsync(VariableScopeNames.Topic));
        }
        else
        {
            Assert.Contains("TestValue", await resumedContext.ReadStateKeysAsync(VariableScopeNames.Topic));
        }
        Assert.Equal(42, await resumedContext.ReadStateAsync<int>("NativeValue", VariableScopeNames.Topic));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task PlainLegacyHelpers_RejectOverlappingMarkedEntriesAsync(bool overwrite)
    {
        // Arrange
        Dictionary<(string? Scope, string Key), PortableValue> values = new()
        {
            [(VariableScopeNames.Local, "TestValue")] = new("local"),
            [(VariableScopeNames.Topic, "TestValue")] = new("legacy"),
        };
        Dictionary<(string? Scope, string Key), SensitivityLevel> sensitivities = new()
        {
            [(WorkflowFormulaState.GetSensitivityScopeName(VariableScopeNames.Local), "TestValue")] = SensitivityLevel.None,
        };
        IWorkflowContext context = CreateStateContext(values, sensitivities).Object;

        // Act
        DeclarativeActionException error = await Assert.ThrowsAsync<DeclarativeActionException>(async () =>
        {
            if (overwrite)
            {
                await context.QueueStateUpdateWithSensitivityAsync("TestValue",
                    new EvaluationResult<object?>("updated", SensitivityLevel.Sensitive), VariableScopeNames.Topic);
            }
            else
            {
                await context.ReadStateWithSensitivityAsync<string>("TestValue", VariableScopeNames.Topic);
            }
        });

        // Assert
        Assert.Contains("conflicting Local and Topic", error.Message);
        Assert.Equal("local", values[(VariableScopeNames.Local, "TestValue")].As<string>());
        Assert.Equal("legacy", values[(VariableScopeNames.Topic, "TestValue")].As<string>());
        Assert.Equal(SensitivityLevel.None, Assert.Single(sensitivities).Value);
    }

    [Theory]
    [InlineData(false, SensitivityLevel.None)]
    [InlineData(false, SensitivityLevel.Sensitive)]
    [InlineData(true, SensitivityLevel.None)]
    [InlineData(true, SensitivityLevel.Sensitive)]
    public async Task LegacyBoundary_ParallelExpressionReadersDoNotWriteStateAsync(bool offThread, SensitivityLevel sensitivity)
    {
        // Arrange
        bool resuming = false;
        int reads = 0;
        IWorkflowContext? resumedContext = null;
        StateExecutor source = new("source", async (context, cancellationToken) =>
        {
            await context.QueueStateUpdateAsync("TestValue", "legacy", VariableScopeNames.Topic, cancellationToken);
            await context.QueueStateUpdateAsync("TestValue", sensitivity,
                WorkflowFormulaState.GetSensitivityScopeName(VariableScopeNames.Local), cancellationToken);
        });
        StateExecutor first = new("first", ReadExpressionAsync);
        StateExecutor second = new("second", ReadExpressionAsync);
        Workflow workflow = new WorkflowBuilder(source).AddEdge(source, first).AddEdge(source, second).Build();
        CheckpointManager checkpoints = CheckpointManager.CreateInMemory();
        var environment = (offThread ? InProcessExecution.OffThread : InProcessExecution.Lockstep).WithCheckpointing(checkpoints);
        CheckpointInfo? checkpoint = null;
        await using (StreamingRun run = await environment.RunStreamingAsync(workflow, 1))
        {
            await foreach (WorkflowEvent evt in run.WatchStreamAsync())
            {
                Assert.False(evt is WorkflowErrorEvent, (evt as WorkflowErrorEvent)?.Exception?.ToString());
                if (evt is SuperStepCompletedEvent { CompletionInfo.Checkpoint: { } saved })
                {
                    checkpoint ??= saved;
                }
            }
        }
        Assert.NotNull(checkpoint);

        // Act
        resuming = true;
        await using StreamingRun resumed = await environment.ResumeStreamingAsync(workflow, checkpoint);
        await foreach (WorkflowEvent evt in resumed.WatchStreamAsync())
        {
            Assert.False(evt is WorkflowErrorEvent, (evt as WorkflowErrorEvent)?.Exception?.ToString());
        }

        // Assert
        Assert.Equal(2, reads);
        Assert.NotNull(resumedContext);
        Assert.Equal("legacy", await resumedContext.ReadStateAsync<string>("TestValue", VariableScopeNames.Topic));
        Assert.DoesNotContain("TestValue", await resumedContext.ReadStateKeysAsync(VariableScopeNames.Local));
        Assert.Equal(sensitivity, await resumedContext.ReadStateAsync<SensitivityLevel>("TestValue",
            WorkflowFormulaState.GetSensitivityScopeName(VariableScopeNames.Local)));

        async ValueTask ReadExpressionAsync(IWorkflowContext context, CancellationToken cancellationToken)
        {
            if (!resuming)
            {
                return;
            }
            EvaluationResult<string?> result = await context.EvaluateValueWithSensitivityAsync<string>("Local.TestValue", cancellationToken);
            Assert.Equal("legacy", result.Value);
            Assert.Equal(sensitivity, result.Sensitivity);
            resumedContext = context;
            Interlocked.Increment(ref reads);
        }
    }

    [Theory]
    [InlineData(false, null)]
    [InlineData(false, VariableScopeNames.Local)]
    [InlineData(false, VariableScopeNames.Topic)]
    [InlineData(true, null)]
    [InlineData(true, VariableScopeNames.Local)]
    [InlineData(true, VariableScopeNames.Topic)]
    public async Task LegacyBoundary_CanonicalWritesRejectUnmarkedTopicCollisionAsync(bool wrapped, string? scopeName)
    {
        // Arrange
        Dictionary<(string? Scope, string Key), PortableValue> values = new()
        {
            [(VariableScopeNames.Local, "TestValue")] = new("existing"),
            [(VariableScopeNames.Topic, "TestValue")] = new("native"),
        };
        Dictionary<(string? Scope, string Key), SensitivityLevel> sensitivities = [];
        IWorkflowContext source = CreateStateContext(values, sensitivities).Object;
        WorkflowFormulaState state = new(RecalcEngineFactory.Create());
        state.Set("TestValue", FormulaValue.New("existing"));
        state.Bind();
        IWorkflowContext context = wrapped ? new DeclarativeWorkflowContext(source, state) : source;

        // Act
        DeclarativeActionException error = await Assert.ThrowsAsync<DeclarativeActionException>(async () =>
            await context.QueueStateUpdateWithSensitivityAsync("TestValue",
                new EvaluationResult<object?>("updated", SensitivityLevel.Sensitive), scopeName));

        // Assert
        Assert.Contains("Topic", error.Message);
        Assert.Equal("existing", values[(VariableScopeNames.Local, "TestValue")].As<string>());
        Assert.Equal("native", values[(VariableScopeNames.Topic, "TestValue")].As<string>());
        Assert.Empty(sensitivities);
        Assert.Equal("existing", state.Get("TestValue").ToObject());
        Assert.Equal(SensitivityLevel.None, state.GetSensitivity("TestValue"));
    }

    [Theory]
    [InlineData(false, SensitivityLevel.None)]
    [InlineData(false, SensitivityLevel.Sensitive)]
    [InlineData(true, SensitivityLevel.None)]
    [InlineData(true, SensitivityLevel.Sensitive)]
    public async Task LegacyBoundary_PlainClearDoesNotClaimReusedTopicKeyAsync(bool overwrite, SensitivityLevel sensitivity)
    {
        // Arrange
        Dictionary<(string? Scope, string Key), PortableValue> values = new()
        {
            [(VariableScopeNames.Local, "TestValue")] = new("before"),
        };
        Dictionary<(string? Scope, string Key), SensitivityLevel> sensitivities = new()
        {
            [(WorkflowFormulaState.GetSensitivityScopeName(VariableScopeNames.Local), "TestValue")] = sensitivity,
        };
        IWorkflowContext context = CreateStateContext(values, sensitivities).Object;
        await context.QueueStateUpdateWithSensitivityAsync("TestValue",
            new EvaluationResult<object?>(null, sensitivity), VariableScopeNames.Topic);
        values[(VariableScopeNames.Topic, "TestValue")] = new("native");

        // Act
        if (overwrite)
        {
            await Assert.ThrowsAsync<DeclarativeActionException>(async () =>
                await context.QueueStateUpdateWithSensitivityAsync("TestValue",
                    new EvaluationResult<object?>("updated", SensitivityLevel.Sensitive), VariableScopeNames.Topic));
        }
        else
        {
            EvaluationResult<string?> result = await context.ReadStateWithSensitivityAsync<string>("TestValue");
            Assert.Null(result.Value);
            Assert.Equal(SensitivityLevel.None, result.Sensitivity);
        }

        // Assert
        Assert.Equal("native", values[(VariableScopeNames.Topic, "TestValue")].As<string>());
        Assert.False(values.ContainsKey((VariableScopeNames.Local, "TestValue")));
        Assert.Empty(sensitivities);
    }

    [Theory]
    [InlineData(false, false, SensitivityLevel.None)]
    [InlineData(false, false, SensitivityLevel.Sensitive)]
    [InlineData(false, true, SensitivityLevel.None)]
    [InlineData(false, true, SensitivityLevel.Sensitive)]
    [InlineData(true, false, SensitivityLevel.None)]
    [InlineData(true, false, SensitivityLevel.Sensitive)]
    [InlineData(true, true, SensitivityLevel.None)]
    [InlineData(true, true, SensitivityLevel.Sensitive)]
    public async Task CanonicalOwnership_MixedFanOutWritesSurviveFreshRestoreAsync(bool offThread, bool wrapped, SensitivityLevel sensitivity)
    {
        // Arrange
        IWorkflowContext? writerContext = null;
        WorkflowFormulaState state = new(RecalcEngineFactory.Create());
        Workflow workflow = CreateWorkflow(state);
        CheckpointManager checkpoints = CreateJsonCheckpointManager();
        var environment = (offThread ? InProcessExecution.OffThread : InProcessExecution.Lockstep).WithCheckpointing(checkpoints);
        CheckpointInfo? checkpoint = null;

        // Act
        await using (StreamingRun run = await environment.RunStreamingAsync(workflow, 1))
        {
            await foreach (WorkflowEvent evt in run.WatchStreamAsync())
            {
                Assert.False(evt is WorkflowErrorEvent, (evt as WorkflowErrorEvent)?.Exception?.ToString());
                if (evt is SuperStepCompletedEvent { CompletionInfo.Checkpoint: { } saved })
                {
                    checkpoint = saved;
                }
            }
        }

        // Assert
        Assert.NotNull(checkpoint);
        Assert.NotNull(writerContext);
        await AssertValuesAsync(writerContext);
        WorkflowFormulaState restoredState = new(RecalcEngineFactory.Create());
        await using StreamingRun resumed = await environment.ResumeStreamingAsync(CreateWorkflow(restoredState), checkpoint);
        Assert.Equal("canonical", restoredState.Get("TestValue").ToObject());
        Assert.Equal(sensitivity, restoredState.GetSensitivity("TestValue"));
        Assert.NotNull(writerContext);
        await AssertValuesAsync(writerContext);

        Workflow CreateWorkflow(WorkflowFormulaState formulaState)
        {
            StateExecutor source = new("source", (_, _) => default);
            StateExecutor raw = new("raw", async (context, cancellationToken) =>
                await context.QueueStateUpdateAsync("TestValue", "native", VariableScopeNames.Topic, cancellationToken));
            StateExecutor canonical = new("canonical", async (context, cancellationToken) =>
            {
                writerContext = context;
                IWorkflowContext target = wrapped ? new DeclarativeWorkflowContext(context, formulaState) : context;
                await target.QueueStateUpdateWithSensitivityAsync("TestValue",
                    new EvaluationResult<object?>("canonical", sensitivity), VariableScopeNames.Topic, cancellationToken);
            }, formulaState, (context, _) =>
            {
                writerContext = context;
                return default;
            });
            return new WorkflowBuilder(source).AddEdge(source, raw).AddEdge(source, canonical).Build();
        }

        async Task AssertValuesAsync(IWorkflowContext context)
        {
            Assert.Equal("native", await context.ReadStateAsync<string>("TestValue", VariableScopeNames.Topic));
            foreach (string? scope in new string?[] { null, VariableScopeNames.Local, VariableScopeNames.Topic })
            {
                EvaluationResult<string?> result = await context.ReadStateWithSensitivityAsync<string>("TestValue", scope);
                Assert.Equal("canonical", result.Value);
                Assert.Equal(sensitivity, result.Sensitivity);
            }
            EvaluationResult<string?> evaluated = await context.EvaluateValueWithSensitivityAsync<string>("Topic.TestValue");
            Assert.Equal("canonical", evaluated.Value);
            Assert.Equal(sensitivity, evaluated.Sensitivity);
        }
    }

    [Theory]
    [InlineData(false, false)]
    [InlineData(false, true)]
    [InlineData(true, false)]
    [InlineData(true, true)]
    public async Task CanonicalOwnership_MixedFanOutInitializationAllowsLaterAssignmentsAsync(bool offThread, bool formula)
    {
        // Arrange
        WorkflowFormulaState state = new(RecalcEngineFactory.Create());
        IWorkflowContext? storedContext = null;
        bool updated = false;
        StateExecutor source = new("source", (_, _) => default);
        StateExecutor raw = new("raw", async (context, cancellationToken) =>
            await context.QueueStateUpdateAsync("TestValue", "native", VariableScopeNames.Topic, cancellationToken));
        StateExecutor initializer = new("initializer", async (context, cancellationToken) =>
        {
            DeclarativeWorkflowContext target = new(context, state);
            if (formula)
            {
                FormulaValue value = await target.ReadOrInitStateAsync<FormulaValue>(
                    "TestValue", () => FormulaValue.New(42), VariableScopeNames.Topic, cancellationToken);
                Assert.Equal(42m, value.ToObject());
            }
            else
            {
                Assert.Equal(42, await target.ReadOrInitStateAsync(
                    "TestValue", () => 42, VariableScopeNames.Topic, cancellationToken));
            }
        }, state);
        StateExecutor writer = new("writer", async (context, cancellationToken) =>
        {
            storedContext = context;
            DeclarativeWorkflowContext target = new(context, state);
            if (formula)
            {
                FormulaValue existing = await target.ReadOrInitStateAsync<FormulaValue>(
                    "TestValue", () => throw new InvalidOperationException("Existing values must not be initialized."),
                    VariableScopeNames.Local, cancellationToken);
                Assert.Equal(42m, existing.ToObject());
            }
            else
            {
                Assert.Equal(42, await context.ReadStateAsync<int>("TestValue", VariableScopeNames.Local, cancellationToken));
                Assert.Equal(42, await target.ReadOrInitStateAsync<int>(
                    "TestValue", () => throw new InvalidOperationException("Existing values must not be initialized."),
                    VariableScopeNames.Local, cancellationToken));
            }
            await target.QueueStateUpdateWithSensitivityAsync("TestValue",
                new EvaluationResult<string>("updated", SensitivityLevel.Sensitive), VariableScopeNames.Topic, cancellationToken);
            updated = true;
        });
        Workflow workflow = new WorkflowBuilder(source)
            .AddEdge(source, raw).AddEdge(source, initializer).AddEdge(initializer, writer).Build();
        var environment = offThread ? InProcessExecution.OffThread : InProcessExecution.Lockstep;

        // Act
        await using StreamingRun run = await environment.RunStreamingAsync(workflow, 1);
        await foreach (WorkflowEvent evt in run.WatchStreamAsync())
        {
            Assert.False(evt is WorkflowErrorEvent, (evt as WorkflowErrorEvent)?.Exception?.ToString());
        }

        // Assert
        Assert.True(updated);
        Assert.NotNull(storedContext);
        Assert.Equal("native", await storedContext.ReadStateAsync<string>("TestValue", VariableScopeNames.Topic));
        WorkflowFormulaState restored = new(RecalcEngineFactory.Create());
        await restored.RestoreSnapshotAsync(storedContext, CancellationToken.None);
        Assert.Equal("updated", restored.Get("TestValue").ToObject());
        Assert.Equal(SensitivityLevel.Sensitive, restored.GetSensitivity("TestValue"));
    }

    [Theory]
    [InlineData(false, false)]
    [InlineData(false, true)]
    [InlineData(true, false)]
    [InlineData(true, true)]
    public async Task CanonicalOwnership_LegacyInitializationPreservesNumericPayloadsAsync(bool offThread, bool formula)
    {
        // Arrange
        object[] values = [42, 42L, 1.5f, 1.5d, 1.5m];
        bool read = false;
        bool restored = false;
        CheckpointManager checkpoints = CreateJsonCheckpointManager();
        var environment = (offThread ? InProcessExecution.OffThread : InProcessExecution.Lockstep).WithCheckpointing(checkpoints);
        CheckpointInfo? checkpoint = null;

        // Act
        await using (StreamingRun run = await environment.RunStreamingAsync(CreateWorkflow(), 1))
        {
            await foreach (WorkflowEvent evt in run.WatchStreamAsync())
            {
                Assert.False(evt is WorkflowErrorEvent, (evt as WorkflowErrorEvent)?.Exception?.ToString());
                if (evt is SuperStepCompletedEvent { CompletionInfo.Checkpoint: { } saved })
                {
                    checkpoint = saved;
                }
            }
        }

        // Assert
        Assert.True(read);
        Assert.NotNull(checkpoint);
        await using StreamingRun resumed = await environment.ResumeStreamingAsync(CreateWorkflow(), checkpoint);
        Assert.True(restored);

        Workflow CreateWorkflow()
        {
            WorkflowFormulaState state = new(RecalcEngineFactory.Create());
            StateExecutor source = new("source", async (context, cancellationToken) =>
            {
                for (int i = 0; i < values.Length; i++)
                {
                    await context.QueueStateUpdateAsync($"Value{i}", values[i], VariableScopeNames.Topic, cancellationToken);
                    await context.QueueStateUpdateAsync($"Value{i}", SensitivityLevel.Sensitive,
                        WorkflowFormulaState.GetSensitivityScopeName(VariableScopeNames.Local), cancellationToken);
                }
            });
            StateExecutor initializer = new("initializer", async (context, cancellationToken) =>
            {
                DeclarativeWorkflowContext target = new(context, state);
                for (int i = 0; i < values.Length; i++)
                {
                    if (formula)
                    {
                        await target.ReadOrInitStateAsync<FormulaValue>(
                            $"Value{i}", () => throw new InvalidOperationException("Existing values must not be initialized."),
                            VariableScopeNames.Topic, cancellationToken);
                    }
                    else
                    {
                        PortableValue result = await target.ReadOrInitStateAsync<PortableValue>(
                            $"Value{i}", () => throw new InvalidOperationException("Existing values must not be initialized."),
                            VariableScopeNames.Topic, cancellationToken);
                        Assert.Equal(values[i], result.AsType(values[i].GetType()));
                    }
                }
            });
            StateExecutor reader = new("reader", async (context, cancellationToken) =>
            {
                await AssertValuesAsync(context, cancellationToken);
                read = true;
            }, restored: async (context, cancellationToken) =>
            {
                await AssertValuesAsync(context, cancellationToken);
                restored = true;
            });
            return new WorkflowBuilder(source).AddEdge(source, initializer).AddEdge(initializer, reader).Build();
        }

        async Task AssertValuesAsync(IWorkflowContext context, CancellationToken cancellationToken)
        {
            Assert.Equal(42, await context.ReadStateAsync<int>("Value0", VariableScopeNames.Local, cancellationToken));
            Assert.Equal(42L, await context.ReadStateAsync<long>("Value1", VariableScopeNames.Local, cancellationToken));
            Assert.Equal(1.5f, await context.ReadStateAsync<float>("Value2", VariableScopeNames.Local, cancellationToken));
            Assert.Equal(1.5d, await context.ReadStateAsync<double>("Value3", VariableScopeNames.Local, cancellationToken));
            Assert.Equal(1.5m, await context.ReadStateAsync<decimal>("Value4", VariableScopeNames.Local, cancellationToken));
            for (int i = 0; i < values.Length; i++)
            {
                EvaluationResult<PortableValue?> result = await context.ReadStateWithSensitivityAsync<PortableValue>(
                    $"Value{i}", VariableScopeNames.Local, cancellationToken);
                Assert.NotNull(result.Value);
                Assert.True(result.Value.TypeId.IsMatch(values[i].GetType()));
                Assert.Equal(values[i], result.Value.AsType(values[i].GetType()));
                Assert.Equal(SensitivityLevel.Sensitive, result.Sensitivity);
            }
            Assert.Empty(await context.ReadStateKeysAsync(VariableScopeNames.Topic, cancellationToken));
        }
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task CanonicalOwnership_InitializationPreservesMarkedLegacyValueAsync(bool formula)
    {
        // Arrange
        Dictionary<(string? Scope, string Key), PortableValue> values = new()
        {
            [(VariableScopeNames.Topic, "TestValue")] = new("legacy"),
        };
        Dictionary<(string? Scope, string Key), SensitivityLevel> sensitivities = new()
        {
            [(WorkflowFormulaState.GetSensitivityScopeName(VariableScopeNames.Local), "TestValue")] = SensitivityLevel.Sensitive,
        };
        IWorkflowContext source = CreateStateContext(values, sensitivities).Object;
        WorkflowFormulaState state = new(RecalcEngineFactory.Create());
        DeclarativeWorkflowContext context = new(source, state);

        // Act
        if (formula)
        {
            FormulaValue result = await context.ReadOrInitStateAsync<FormulaValue>(
                "TestValue", () => FormulaValue.New("replacement"), VariableScopeNames.Topic);
            Assert.Equal("legacy", result.ToObject());
        }
        else
        {
            Assert.Equal("legacy", await context.ReadOrInitStateAsync("TestValue", () => "replacement", VariableScopeNames.Topic));
        }

        // Assert
        EvaluationResult<string?> restored = await source.ReadStateWithSensitivityAsync<string>("TestValue");
        Assert.Equal("legacy", restored.Value);
        Assert.Equal(SensitivityLevel.Sensitive, restored.Sensitivity);
        Assert.Equal(SensitivityLevel.Sensitive, state.GetSensitivity("TestValue"));
        Assert.False(values.ContainsKey((VariableScopeNames.Topic, "TestValue")));
    }

    [Theory]
    [InlineData(SensitivityLevel.None)]
    [InlineData(SensitivityLevel.Sensitive)]
    public async Task CanonicalOwnership_MigrationDoesNotClaimLaterRawTopicReuseAsync(SensitivityLevel sensitivity)
    {
        // Arrange
        Dictionary<(string? Scope, string Key), PortableValue> values = new()
        {
            [(VariableScopeNames.Topic, "TestValue")] = new("legacy"),
        };
        Dictionary<(string? Scope, string Key), SensitivityLevel> sensitivities = new()
        {
            [(WorkflowFormulaState.GetSensitivityScopeName(VariableScopeNames.Local), "TestValue")] = sensitivity,
        };
        IWorkflowContext context = CreateStateContext(values, sensitivities).Object;
        WorkflowFormulaState state = new(RecalcEngineFactory.Create());
        await state.RestoreCheckpointAsync(context, CancellationToken.None);
        values[(VariableScopeNames.Topic, "TestValue")] = new("native");

        // Act
        await state.RestoreCheckpointAsync(context, CancellationToken.None);
        EvaluationResult<string?> result = await context.ReadStateWithSensitivityAsync<string>("TestValue");

        // Assert
        Assert.Equal("legacy", result.Value);
        Assert.Equal(sensitivity, result.Sensitivity);
        Assert.Equal("legacy", state.Get("TestValue").ToObject());
        Assert.Equal(sensitivity, state.GetSensitivity("TestValue"));
        Assert.Equal("native", values[(VariableScopeNames.Topic, "TestValue")].As<string>());
    }

    [Theory]
    [InlineData(false, SensitivityLevel.None)]
    [InlineData(false, SensitivityLevel.Sensitive)]
    [InlineData(true, SensitivityLevel.None)]
    [InlineData(true, SensitivityLevel.Sensitive)]
    public async Task CanonicalOwnership_UpdatesAndClearsPreserveRawTopicStateAsync(bool wrapped, SensitivityLevel sensitivity)
    {
        // Arrange
        Dictionary<(string? Scope, string Key), PortableValue> values = [];
        Dictionary<(string? Scope, string Key), SensitivityLevel> sensitivities = [];
        IWorkflowContext source = CreateStateContext(values, sensitivities).Object;
        WorkflowFormulaState state = new(RecalcEngineFactory.Create());
        IWorkflowContext context = wrapped ? new DeclarativeWorkflowContext(source, state) : source;
        await context.QueueStateUpdateWithSensitivityAsync("TestValue",
            new EvaluationResult<object?>("initial", sensitivity), VariableScopeNames.Local);
        values[(VariableScopeNames.Topic, "TestValue")] = new("native");

        // Act
        await context.QueueStateUpdateWithSensitivityAsync("TestValue",
            new EvaluationResult<object?>("updated", sensitivity), VariableScopeNames.Topic);
        EvaluationResult<string?> updated = await source.ReadStateWithSensitivityAsync<string>("TestValue");
        await context.QueueStateUpdateWithSensitivityAsync("TestValue",
            new EvaluationResult<object?>(null, sensitivity), VariableScopeNames.Local);
        await state.RestoreSnapshotAsync(source, CancellationToken.None);

        // Assert
        Assert.Equal("updated", updated.Value);
        Assert.Equal(sensitivity, updated.Sensitivity);
        Assert.Equal("native", values[(VariableScopeNames.Topic, "TestValue")].As<string>());
        Assert.IsType<BlankValue>(state.Get("TestValue"));
        if (wrapped)
        {
            Assert.Equal(sensitivity, state.GetSensitivity("TestValue"));
        }
        else
        {
            EvaluationResult<string?> cleared = await source.ReadStateWithSensitivityAsync<string>("TestValue");
            Assert.Null(cleared.Value);
            Assert.Equal(SensitivityLevel.None, cleared.Sensitivity);
            Assert.Empty(sensitivities);
            await Assert.ThrowsAsync<DeclarativeActionException>(async () =>
                await source.QueueStateUpdateWithSensitivityAsync("TestValue",
                    new EvaluationResult<object?>("replacement", sensitivity)));
        }
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task CanonicalOwnership_PointOperationsUseBoundedKeyLookupsAsync(bool wrapped)
    {
        // Arrange
        const int Assignments = 32;
        Dictionary<(string? Scope, string Key), PortableValue> values = [];
        Dictionary<(string? Scope, string Key), SensitivityLevel> sensitivities = [];
        Mock<IWorkflowContext> source = CreateStateContext(values, sensitivities);
        IWorkflowContext context = wrapped ? new DeclarativeWorkflowContext(source.Object, new(RecalcEngineFactory.Create())) : source.Object;

        // Act
        for (int i = 0; i < Assignments; ++i)
        {
            string key = $"Value{i}";
            await context.QueueStateUpdateWithSensitivityAsync(key,
                new EvaluationResult<object?>("value", SensitivityLevel.None), VariableScopeNames.Local);
            EvaluationResult<string?> result = await source.Object.ReadStateWithSensitivityAsync<string>(key, VariableScopeNames.Topic);
            Assert.Equal("value", result.Value);
        }

        // Assert
        source.Verify(c => c.ReadStateKeysAsync(It.IsAny<string?>(), It.IsAny<CancellationToken>()), Times.Never);
        source.Verify(c => c.ReadStateAsync<PortableValue>(It.IsAny<string>(), It.IsAny<string?>(), It.IsAny<CancellationToken>()),
            Times.AtMost(Assignments * 8));
    }

    [Theory]
    [InlineData(false, false)]
    [InlineData(false, true)]
    [InlineData(true, false)]
    [InlineData(true, true)]
    public async Task CanonicalOwnership_UnsupportedVersionsDoNotDisambiguateStateAsync(bool restore, bool overwrite)
    {
        // Arrange
        Dictionary<(string? Scope, string Key), PortableValue> values = new()
        {
            [(VariableScopeNames.Local, "TestValue")] = new("canonical"),
            [(VariableScopeNames.Topic, "TestValue")] = new("native"),
            [(WorkflowFormulaState.LocalOwnershipScopeName, "TestValue")] = new(2),
        };
        Dictionary<(string? Scope, string Key), SensitivityLevel> sensitivities = new()
        {
            [(WorkflowFormulaState.GetSensitivityScopeName(VariableScopeNames.Local), "TestValue")] = SensitivityLevel.None,
        };
        IWorkflowContext context = CreateStateContext(values, sensitivities).Object;
        WorkflowFormulaState state = new(RecalcEngineFactory.Create());

        // Act
        DeclarativeActionException error = await Assert.ThrowsAsync<DeclarativeActionException>(async () =>
        {
            if (restore)
            {
                if (overwrite)
                {
                    await state.RestoreCheckpointAsync(context, CancellationToken.None);
                }
                else
                {
                    await state.RestoreSnapshotAsync(context, CancellationToken.None);
                }
            }
            else if (overwrite)
            {
                await context.QueueStateUpdateWithSensitivityAsync("TestValue",
                    new EvaluationResult<object?>("replacement", SensitivityLevel.Sensitive));
            }
            else
            {
                await context.ReadStateWithSensitivityAsync<string>("TestValue");
            }
        });

        // Assert
        Assert.Contains("Unsupported declarative state ownership version", error.Message);
        Assert.Equal("canonical", values[(VariableScopeNames.Local, "TestValue")].As<string>());
        Assert.Equal("native", values[(VariableScopeNames.Topic, "TestValue")].As<string>());
        Assert.Equal(2, values[(WorkflowFormulaState.LocalOwnershipScopeName, "TestValue")].As<int>());
        Assert.Equal(SensitivityLevel.None, Assert.Single(sensitivities).Value);
    }

    private static CheckpointManager CreateJsonCheckpointManager()
    {
        Dictionary<CheckpointInfo, JsonElement> stored = [];
        Mock<ICheckpointStore<JsonElement>> store = new();
        store.Setup(s => s.CreateCheckpointAsync(It.IsAny<string>(), It.IsAny<JsonElement>(), It.IsAny<CheckpointInfo?>()))
            .ReturnsAsync((string sessionId, JsonElement value, CheckpointInfo? _) =>
            {
                CheckpointInfo info = new(sessionId, Guid.NewGuid().ToString("N"));
                stored.Add(info, value);
                return info;
            });
        store.Setup(s => s.RetrieveCheckpointAsync(It.IsAny<string>(), It.IsAny<CheckpointInfo>()))
            .ReturnsAsync((string _, CheckpointInfo info) => stored[info]);
        store.Setup(s => s.RetrieveIndexAsync(It.IsAny<string>(), It.IsAny<CheckpointInfo?>()))
            .ReturnsAsync((string sessionId, CheckpointInfo? _) =>
                stored.Keys.Where(info => string.Equals(info.SessionId, sessionId, StringComparison.Ordinal)).ToArray().AsEnumerable());
        return CheckpointManager.CreateJson(store.Object, DeclarativeWorkflowJsonOptions.Default);
    }

    private static async ValueTask SeedLegacyStateAsync(IWorkflowContext context, CancellationToken cancellationToken)
    {
        await context.QueueStateUpdateAsync("TestValue", "legacy", VariableScopeNames.Topic, cancellationToken);
        await context.QueueStateUpdateAsync("TestValue", SensitivityLevel.Sensitive,
            WorkflowFormulaState.GetSensitivityScopeName(VariableScopeNames.Local), cancellationToken);
    }

    private sealed class StateExecutor : Executor<int>, IResettableExecutor
    {
        private readonly Func<IWorkflowContext, CancellationToken, ValueTask> _handle;
        private readonly Func<IWorkflowContext, CancellationToken, ValueTask>? _restored;

        public StateExecutor(
            string id,
            Func<IWorkflowContext, CancellationToken, ValueTask> handle,
            WorkflowFormulaState? state = null,
            Func<IWorkflowContext, CancellationToken, ValueTask>? restored = null) : base(id)
        {
            this._handle = handle;
            this._restored = restored;
            if (state is not null)
            {
                this.RegisterCheckpointRestoringCallback(state, state.RestoreCheckpointAsync);
            }
        }

        public ValueTask ResetAsync() => default;

        [SendsMessage(typeof(int))]
        public override async ValueTask HandleAsync(int message, IWorkflowContext context, CancellationToken cancellationToken = default)
        {
            await this._handle(context, cancellationToken);
            await context.SendMessageAsync(message, cancellationToken: cancellationToken);
        }

        protected override ValueTask OnCheckpointRestoredAsync(IWorkflowContext context, CancellationToken cancellationToken = default) =>
            this._restored?.Invoke(context, cancellationToken) ?? default;
    }

    private static Mock<IWorkflowContext> CreateStateContext(
        Dictionary<(string? Scope, string Key), PortableValue> values,
        Dictionary<(string? Scope, string Key), SensitivityLevel> sensitivities)
    {
        Mock<IWorkflowContext> source = new(MockBehavior.Strict);
        source.Setup(c => c.QueueStateUpdateAsync(It.IsAny<string>(), It.IsAny<object?>(), It.IsAny<string?>(), It.IsAny<CancellationToken>()))
            .Callback((string key, object? value, string? scope, CancellationToken _) =>
            {
                if (value is null)
                {
                    values.Remove((scope, key));
                    sensitivities.Remove((scope, key));
                }
                else
                {
                    values[(scope, key)] = new PortableValue(value);
                }
            })
            .Returns(default(ValueTask));
        source.Setup(c => c.QueueStateUpdateAsync(It.IsAny<string>(), It.IsAny<UnassignedValue>(), It.IsAny<string?>(), It.IsAny<CancellationToken>()))
            .Callback((string key, UnassignedValue value, string? scope, CancellationToken _) => values[(scope, key)] = new(value))
            .Returns(default(ValueTask));
        source.Setup(c => c.QueueStateUpdateAsync(It.IsAny<string>(), It.IsAny<SensitivityLevel>(), It.IsAny<string?>(), It.IsAny<CancellationToken>()))
            .Callback((string key, SensitivityLevel value, string? scope, CancellationToken _) => sensitivities[(scope, key)] = value)
            .Returns(default(ValueTask));
        source.Setup(c => c.QueueStateUpdateAsync(It.IsAny<string>(), It.IsAny<int>(), It.IsAny<string?>(), It.IsAny<CancellationToken>()))
            .Callback((string key, int value, string? scope, CancellationToken _) => values[(scope, key)] = new(value))
            .Returns(default(ValueTask));
        source.Setup(c => c.QueueClearScopeAsync(It.IsAny<string?>(), It.IsAny<CancellationToken>()))
            .Callback((string? scope, CancellationToken _) =>
            {
                foreach (var key in values.Keys.Where(key => string.Equals(key.Scope, scope, StringComparison.Ordinal)).ToArray())
                {
                    values.Remove(key);
                }
            })
            .Returns(default(ValueTask));
        source.Setup(c => c.ReadStateKeysAsync(It.IsAny<string?>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync((string? scope, CancellationToken _) => values.Keys.Concat(sensitivities.Keys)
                .Where(k => string.Equals(k.Scope, scope, StringComparison.Ordinal)).Select(k => k.Key).ToHashSet());
        source.Setup(c => c.ReadStateAsync<PortableValue>(It.IsAny<string>(), It.IsAny<string?>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync((string key, string? scope, CancellationToken _) => values.TryGetValue((scope, key), out PortableValue? value)
                ? value : sensitivities.TryGetValue((scope, key), out SensitivityLevel sensitivity) ? new PortableValue(sensitivity) : null);
        source.Setup(c => c.ReadStateAsync<SensitivityLevel>(It.IsAny<string>(), It.IsAny<string?>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync((string key, string? scope, CancellationToken _) => sensitivities.TryGetValue((scope, key), out SensitivityLevel sensitivity) ? sensitivity : SensitivityLevel.None);
        source.Setup(c => c.ReadStateAsync<string>(It.IsAny<string>(), It.IsAny<string?>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync((string key, string? scope, CancellationToken _) => values.TryGetValue((scope, key), out PortableValue? value) ? value.As<string>() : null);
        source.Setup(c => c.ReadOrInitStateAsync(It.IsAny<string>(), It.IsAny<Func<string>>(), It.IsAny<string?>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync((string key, Func<string> factory, string? scope, CancellationToken _) => values.TryGetValue((scope, key), out PortableValue? value) ? Assert.IsType<string>(value.As<string>()) : factory());
        return source;
    }
}
