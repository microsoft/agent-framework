// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

public class ExecutorTestsBase
{
    public sealed record TextMessage(string Text);

    public const string TestMessageContent = nameof(TestMessage);
    public static TextMessage TestMessage { get; } = new(TestMessageContent);

    [System.Diagnostics.CodeAnalysis.SuppressMessage("Performance", "CA1819:Properties should not return arrays", Justification = "Test Object")]
    public sealed record DataMessage(string Base64Bytes)
    {
        private static string ToBase64String(string text, Encoding? expectedEncoding)
        {
            byte[] bytes = (expectedEncoding ?? Encoding.UTF8).GetBytes(text);
            return Convert.ToBase64String(bytes);
        }

        public DataMessage(TextMessage textMessage, Encoding? expectedEncoding = null) : this(ToBase64String(textMessage.Text, expectedEncoding))
        { }
    }

    public const string DataMessageContent = nameof(DataMessage);
    public static DataMessage TestDataMessage { get; } = new(TestMessage);

    public sealed class InvocationEvent<TMessage>(TMessage message) : WorkflowEvent(message)
    {
        public TMessage Message => message;
    }

    internal sealed record ExecutorTestResult(TestWorkflowContext Context, object? CallResult);

    internal async ValueTask<ExecutorTestResult> Run_FunctionExecutor_MessageHandlerTestAsync<TMessage>(Executor executor, TMessage message, CancellationToken cancellationToken = default)
        where TMessage : notnull
    {
        TestWorkflowContext workflowContext = this.CreateWorkflowContext(executor);
        _ = executor.DescribeProtocol();

        object? result = await executor.ExecuteCoreAsync(message, new(typeof(TMessage)), workflowContext, cancellationToken);

        return new(workflowContext, result);
    }

    internal static void CheckInvoked<TMessage>(ExecutorTestResult result, TMessage expectedInput, object? expectedCallResult = null)
        where TMessage : class
    {
        Assert.Equal(expectedCallResult, result.CallResult);

        Assert.Contains(result.Context.EmittedEvents, evt => evt is ExecutorInvokedEvent invoked
                               && MatchesExpected(invoked.Data, expectedInput));
        Assert.Contains(result.Context.EmittedEvents, evt => evt is ExecutorCompletedEvent completed
                               && ReferenceEquals(completed.Data, result.CallResult));
    }

    internal static void CheckInvoked<TMessage, TOutput>(ExecutorTestResult result, TMessage expectedInput, TOutput expectedCallResult)
        where TMessage : class
        where TOutput : class
    {
        Assert.Equal(expectedCallResult, result.CallResult);

        Assert.Contains(result.Context.EmittedEvents, evt => evt is ExecutorInvokedEvent invoked
                               && MatchesExpected(invoked.Data, expectedInput));
        Assert.Contains(result.Context.EmittedEvents, evt => evt is ExecutorCompletedEvent completed
                               && ReferenceEquals(completed.Data, result.CallResult));
    }

    private static bool MatchesExpected<TExpected>(object? actual, TExpected expected)
        where TExpected : class
    {
        return actual as TExpected == expected;
    }

    internal TestWorkflowContext CreateWorkflowContext(Executor executor) => new(executor.Id);
}

public class FunctionExecutorTests : ExecutorTestsBase
{
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task Test_FunctionExecutor__1_InvokesDelegateSuccessfullyAsync(bool useAsync)
    {
        // Arrange
        FunctionExecutor<TextMessage> executor = useAsync
                                               ? new(nameof(FunctionExecutor<>), MessageHandlerAsync)
                                               : new(nameof(FunctionExecutor<>), MessageHandler);

        // Act
        ExecutorTestResult result = await this.Run_FunctionExecutor_MessageHandlerTestAsync(executor, TestMessage);

        // Assert
        CheckInvoked(result, TestMessage);

        // Helpers
        ValueTask MessageHandlerAsync(TextMessage message, IWorkflowContext context, CancellationToken cancellationToken)
            => default;

        void MessageHandler(TextMessage message, IWorkflowContext context, CancellationToken cancellationToken) { }
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task Test_FunctionExecutor__2_InvokesDelegateSuccessfullyAsync(bool useAsync)
    {
        // Arrange
        FunctionExecutor<TextMessage, DataMessage> executor = useAsync
                                                            ? new(nameof(FunctionExecutor<,>), MessageHandlerAsync)
                                                            : new(nameof(FunctionExecutor<,>), MessageHandler);

        // Act
        ExecutorTestResult result = await this.Run_FunctionExecutor_MessageHandlerTestAsync(executor, TestMessage);

        // Assert
        CheckInvoked(result, TestMessage, TestDataMessage);

        // Helpers
        ValueTask<DataMessage> MessageHandlerAsync(TextMessage message, IWorkflowContext context, CancellationToken cancellationToken)
            => new(new DataMessage(message));

        DataMessage MessageHandler(TextMessage message, IWorkflowContext context, CancellationToken cancellationToken)
            => new(message);
    }

    [Theory]
    [InlineData(false, false)]
    [InlineData(false, true)]
    [InlineData(true, false)]
    [InlineData(true, true)]
    public void Test_FunctionExecutor__1_SendTypesAreRegistered(bool useAsync, bool useAnnotated)
    {
        // Arrange
        IEnumerable<Type>? sendTypes = useAnnotated
                                     ? null
                                     : [typeof(TextMessage)];

        FunctionExecutor<TextMessage> executor = useAsync
                                               ? new(nameof(FunctionExecutor<>), useAnnotated ? MessageHandlerAnnotatedAsync
                                                                                              : MessageHandlerAsync, sentMessageTypes: sendTypes)
                                               : new(nameof(FunctionExecutor<>), useAnnotated ? MessageHandlerAnnotated
                                                                                              : MessageHandler, sentMessageTypes: sendTypes);

        // Act
        ProtocolDescriptor protocol = executor.DescribeProtocol();

        // Assert
        Assert.Equivalent(new[] { typeof(TextMessage) }, protocol.Sends);
        Assert.Empty(protocol.Yields ?? []);

        // Helpers
        [SendsMessage(typeof(TextMessage))]
        ValueTask MessageHandlerAnnotatedAsync(TextMessage message, IWorkflowContext context, CancellationToken cancellationToken)
            => MessageHandlerAsync(message, context, cancellationToken);

        ValueTask MessageHandlerAsync(TextMessage message, IWorkflowContext context, CancellationToken cancellationToken)
            => context.SendMessageAsync(message, cancellationToken);

        [SendsMessage(typeof(TextMessage))]
        void MessageHandlerAnnotated(TextMessage message, IWorkflowContext context, CancellationToken cancellationToken)
            => MessageHandler(message, context, cancellationToken);

#pragma warning disable VSTHRD002 // Avoid problematic synchronous waits
        void MessageHandler(TextMessage message, IWorkflowContext context, CancellationToken cancellationToken)
            => context.SendMessageAsync(message, cancellationToken).AsTask().GetAwaiter().GetResult();
#pragma warning restore VSTHRD002 // Avoid problematic synchronous waits
    }

    [Theory]
    [InlineData(false, false)]
    [InlineData(false, true)]
    [InlineData(true, false)]
    [InlineData(true, true)]
    public void Test_FunctionExecutor__2_SendTypesAreRegistered(bool useAsync, bool useAnnotated)
    {
        // Arrange
        ExecutorOptions options = new()
        {
            AutoSendMessageHandlerResultObject = false,
            AutoYieldOutputHandlerResultObject = false
        };

        IEnumerable<Type>? sendTypes = useAnnotated
                                     ? null
                                     : [typeof(TextMessage)];

        FunctionExecutor<TextMessage, DataMessage> executor
            = useAsync
            ? new(nameof(FunctionExecutor<,>), useAnnotated ? MessageHandlerAnnotatedAsync
                                                            : MessageHandlerAsync, options, sentMessageTypes: sendTypes)
            : new(nameof(FunctionExecutor<,>), useAnnotated ? MessageHandlerAnnotated
                                                            : MessageHandler, options, sentMessageTypes: sendTypes);

        // Act
        ProtocolDescriptor protocol = executor.DescribeProtocol();

        // Assert
        Assert.Equivalent(new[] { typeof(TextMessage) }, protocol.Sends);
        Assert.Empty(protocol.Yields ?? []);

        // Helpers
        [SendsMessage(typeof(TextMessage))]
        ValueTask<DataMessage> MessageHandlerAnnotatedAsync(TextMessage message, IWorkflowContext context, CancellationToken cancellationToken)
            => MessageHandlerAsync(message, context, cancellationToken);

        async ValueTask<DataMessage> MessageHandlerAsync(TextMessage message, IWorkflowContext context, CancellationToken cancellationToken)
        {
            await context.SendMessageAsync(message, cancellationToken);
            return new(message);
        }

        [SendsMessage(typeof(TextMessage))]
        DataMessage MessageHandlerAnnotated(TextMessage message, IWorkflowContext context, CancellationToken cancellationToken)
            => MessageHandler(message, context, cancellationToken);

#pragma warning disable VSTHRD002 // Avoid problematic synchronous waits
        DataMessage MessageHandler(TextMessage message, IWorkflowContext context, CancellationToken cancellationToken)
        {
            context.SendMessageAsync(message, cancellationToken).AsTask().GetAwaiter().GetResult();
            return new(message);
        }
#pragma warning restore VSTHRD002 // Avoid problematic synchronous waits
    }

    [Theory]
    [InlineData(false, false)]
    [InlineData(false, true)]
    [InlineData(true, false)]
    [InlineData(true, true)]
    public void Test_FunctionExecutor__1_YieldTypesAreRegistered(bool useAsync, bool useAnnotated)
    {
        // Arrange
        IEnumerable<Type>? yieldTypes = useAnnotated
                                      ? null
                                      : [typeof(DataMessage)];

        FunctionExecutor<TextMessage> executor = useAsync
                                               ? new(nameof(FunctionExecutor<>), useAnnotated ? MessageHandlerAnnotatedAsync
                                                                                              : MessageHandlerAsync, outputTypes: yieldTypes)
                                               : new(nameof(FunctionExecutor<>), useAnnotated ? MessageHandlerAnnotated
                                                                                              : MessageHandler, outputTypes: yieldTypes);

        // Act
        ProtocolDescriptor protocol = executor.DescribeProtocol();

        // Assert
        Assert.Equivalent(new[] { typeof(DataMessage) }, protocol.Yields);
        Assert.Empty(protocol.Sends ?? []);

        // Helpers
        [YieldsOutput(typeof(DataMessage))]
        ValueTask MessageHandlerAnnotatedAsync(TextMessage message, IWorkflowContext context, CancellationToken cancellationToken)
            => MessageHandlerAsync(message, context, cancellationToken);

        ValueTask MessageHandlerAsync(TextMessage message, IWorkflowContext context, CancellationToken cancellationToken)
            => context.YieldOutputAsync(new DataMessage(message), cancellationToken);

        [YieldsOutput(typeof(DataMessage))]
        void MessageHandlerAnnotated(TextMessage message, IWorkflowContext context, CancellationToken cancellationToken)
            => MessageHandler(message, context, cancellationToken);

#pragma warning disable VSTHRD002 // Avoid problematic synchronous waits
        void MessageHandler(TextMessage message, IWorkflowContext context, CancellationToken cancellationToken)
            => context.YieldOutputAsync(new DataMessage(message), cancellationToken).AsTask().GetAwaiter().GetResult();
#pragma warning restore VSTHRD002 // Avoid problematic synchronous waits
    }

    [Theory]
    [InlineData(false, false)]
    [InlineData(false, true)]
    [InlineData(true, false)]
    [InlineData(true, true)]
    public void Test_FunctionExecutor__2_YieldTypesAreRegistered(bool useAsync, bool useAnnotated)
    {
        // Arrange
        ExecutorOptions options = new()
        {
            AutoSendMessageHandlerResultObject = false,
            AutoYieldOutputHandlerResultObject = false
        };

        IEnumerable<Type>? yieldTypes = useAnnotated
                                      ? null
                                      : [typeof(DataMessage)];

        FunctionExecutor<TextMessage, DataMessage> executor
            = useAsync
            ? new(nameof(FunctionExecutor<>), useAnnotated ? MessageHandlerAnnotatedAsync
                                                           : MessageHandlerAsync, options, outputTypes: yieldTypes)
            : new(nameof(FunctionExecutor<>), useAnnotated ? MessageHandlerAnnotated
                                                           : MessageHandler, options, outputTypes: yieldTypes);

        // Act
        ProtocolDescriptor protocol = executor.DescribeProtocol();

        // Assert
        Assert.Equivalent(new[] { typeof(DataMessage) }, protocol.Yields);
        Assert.Empty(protocol.Sends ?? []);

        // Helpers
        [YieldsOutput(typeof(DataMessage))]
        ValueTask<DataMessage> MessageHandlerAnnotatedAsync(TextMessage message, IWorkflowContext context, CancellationToken cancellationToken)
            => MessageHandlerAsync(message, context, cancellationToken);

        async ValueTask<DataMessage> MessageHandlerAsync(TextMessage message, IWorkflowContext context, CancellationToken cancellationToken)
        {
            await context.YieldOutputAsync(new DataMessage(message), cancellationToken);
            return new(message);
        }

        [YieldsOutput(typeof(DataMessage))]
        DataMessage MessageHandlerAnnotated(TextMessage message, IWorkflowContext context, CancellationToken cancellationToken)
            => MessageHandler(message, context, cancellationToken);

#pragma warning disable VSTHRD002 // Avoid problematic synchronous waits
        DataMessage MessageHandler(TextMessage message, IWorkflowContext context, CancellationToken cancellationToken)
        {
            context.YieldOutputAsync(new DataMessage(message), cancellationToken).AsTask().GetAwaiter().GetResult();
            return new(message);
        }
#pragma warning restore VSTHRD002 // Avoid problematic synchronous waits
    }

    [Theory]
    [InlineData(false, false, false)]
    [InlineData(false, false, true)]
    [InlineData(false, true, false)]
    [InlineData(false, true, true)]
    [InlineData(true, false, false)]
    [InlineData(true, false, true)]
    [InlineData(true, true, false)]
    [InlineData(true, true, true)]
    public void Test_FunctionExecutor__1_ExecutorOptionsAreNoOp(bool useAsync, bool autoSendReturnValue, bool autoYieldReturnValue)
    {
        // Because FunctionExecutor<TInput> does not have a rail for a returned value, setting up options for it will
        // not register any output types
        ExecutorOptions options = new()
        {
            AutoSendMessageHandlerResultObject = autoSendReturnValue,
            AutoYieldOutputHandlerResultObject = autoYieldReturnValue
        };

        FunctionExecutor<TextMessage> executor = useAsync
                                               ? new(nameof(FunctionExecutor<>), MessageHandlerAsync, options)
                                               : new(nameof(FunctionExecutor<>), MessageHandler, options);

        ProtocolDescriptor protocol = executor.DescribeProtocol();
        Assert.Empty(protocol.Sends ?? []);
        Assert.Empty(protocol.Yields ?? []);

        // Helpers
        ValueTask MessageHandlerAsync(TextMessage message, IWorkflowContext context, CancellationToken cancellationToken)
            => context.SendMessageAsync(message, cancellationToken);

#pragma warning disable VSTHRD002 // Avoid problematic synchronous waits
        void MessageHandler(TextMessage message, IWorkflowContext context, CancellationToken cancellationToken)
            => context.SendMessageAsync(message, cancellationToken).AsTask().GetAwaiter().GetResult();
#pragma warning restore VSTHRD002 // Avoid problematic synchronous waits
    }

    [Theory]
    [InlineData(false, false, false)]
    [InlineData(false, false, true)]
    [InlineData(false, true, false)]
    [InlineData(false, true, true)]
    [InlineData(true, false, false)]
    [InlineData(true, false, true)]
    [InlineData(true, true, false)]
    [InlineData(true, true, true)]
    public async Task Test_FunctionExecutor__2_ExecutorOptionsCauseCorrectRegistration_AndAutoBehaviorAsync(bool useAsync, bool autoSendReturnValue, bool autoYieldReturnValue)
    {
        // Arrange
        // Because FunctionExecutor<TInput> does not have a rail for a returned value, setting up options for it will
        // not register any output types
        ExecutorOptions options = new()
        {
            AutoSendMessageHandlerResultObject = autoSendReturnValue,
            AutoYieldOutputHandlerResultObject = autoYieldReturnValue
        };

        FunctionExecutor<TextMessage, DataMessage> executor = useAsync
                                                            ? new(nameof(FunctionExecutor<>), MessageHandlerAsync, options)
                                                            : new(nameof(FunctionExecutor<>), MessageHandler, options);

        // Act
        ExecutorTestResult result = await this.Run_FunctionExecutor_MessageHandlerTestAsync(executor, TestMessage);
        ProtocolDescriptor protocol = executor.DescribeProtocol();

        // Assert
        CheckInvoked(result, TestMessage, TestDataMessage);
        if (autoSendReturnValue)
        {
            Assert.Equivalent(new[] { typeof(DataMessage) }, protocol.Sends);
            Assert.Contains(result.Context.SentMessages, IsTestDataMessage);
        }
        else
        {
            Assert.Empty(protocol.Sends ?? []);
            Assert.DoesNotContain(result.Context.SentMessages, IsTestDataMessage);
        }

        if (autoYieldReturnValue)
        {
            Assert.Equivalent(new[] { typeof(DataMessage) }, protocol.Yields);
            Assert.Contains(result.Context.YieldedOutputs, IsTestDataMessage);
        }
        else
        {
            Assert.Empty(protocol.Yields ?? []);
            Assert.DoesNotContain(result.Context.YieldedOutputs, IsTestDataMessage);
        }

        static bool IsTestDataMessage(object message)
            => TestDataMessage.Equals(message is PortableValue portableValue ? portableValue.As<DataMessage>() : message);

        // Helpers
        ValueTask<DataMessage> MessageHandlerAsync(TextMessage message, IWorkflowContext context, CancellationToken cancellationToken)
            => new(new DataMessage(message));

        DataMessage MessageHandler(TextMessage message, IWorkflowContext context, CancellationToken cancellationToken)
            => new(message);
    }
}
