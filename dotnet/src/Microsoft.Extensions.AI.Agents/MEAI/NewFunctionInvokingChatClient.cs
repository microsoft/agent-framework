// Copyright (c) Microsoft. All rights reserved.

// WARNING:
// This class is a copy of FunctionInvokingChatClient from MEAI, and is intended to be modified with
// changes that we want to prototype here, before updating FunctionInvokingChatClient in MEAI.
// The intention is to keep the changes in this file to a minimum, so that we can easily
// merge them back into MEAI when ready.

// AF repo suppressions for code copied from MEAI.
#pragma warning disable IDE1006 // Naming Styles
#pragma warning disable IDE0009 // Member access should be qualified.
#pragma warning disable CA2007 // Consider calling ConfigureAwait on the awaited task
#pragma warning disable VSTHRD111 // Use ConfigureAwait(bool)

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Runtime.ExceptionServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Shared.Diagnostics;

#pragma warning disable CA2213 // Disposable fields should be disposed
#pragma warning disable EA0002 // Use 'System.TimeProvider' to make the code easier to test
#pragma warning disable SA1202 // 'protected' members should come before 'private' members
#pragma warning disable S107 // Methods should not have too many parameters

namespace Microsoft.Extensions.AI;

/// <summary>
/// A delegating chat client that invokes functions defined on <see cref="ChatOptions"/>.
/// Include this in a chat pipeline to resolve function calls automatically.
/// </summary>
/// <remarks>
/// <para>
/// When this client receives a <see cref="FunctionCallContent"/> in a chat response, it responds
/// by calling the corresponding <see cref="AIFunction"/> defined in <see cref="ChatOptions.Tools"/>,
/// producing a <see cref="FunctionResultContent"/> that it sends back to the inner client. This loop
/// is repeated until there are no more function calls to make, or until another stop condition is met,
/// such as hitting <see cref="MaximumIterationsPerRequest"/>.
/// </para>
/// <para>
/// The provided implementation of <see cref="IChatClient"/> is thread-safe for concurrent use so long as the
/// <see cref="AIFunction"/> instances employed as part of the supplied <see cref="ChatOptions"/> are also safe.
/// The <see cref="AllowConcurrentInvocation"/> property can be used to control whether multiple function invocation
/// requests as part of the same request are invocable concurrently, but even with that set to <see langword="false"/>
/// (the default), multiple concurrent requests to this same instance and using the same tools could result in those
/// tools being used concurrently (one per request). For example, a function that accesses the HttpContext of a specific
/// ASP.NET web request should only be used as part of a single <see cref="ChatOptions"/> at a time, and only with
/// <see cref="AllowConcurrentInvocation"/> set to <see langword="false"/>, in case the inner client decided to issue multiple
/// invocation requests to that same function.
/// </para>
/// </remarks>
public partial class NewFunctionInvokingChatClient : DelegatingChatClient
{
    /// <summary>The <see cref="FunctionInvocationContext"/> for the current function invocation.</summary>
    private static readonly AsyncLocal<FunctionInvocationContext?> _currentContext = new();

    /// <summary>Gets the <see cref="IServiceProvider"/> specified when constructing the <see cref="FunctionInvokingChatClient"/>, if any.</summary>
    protected IServiceProvider? FunctionInvocationServices { get; }

    /// <summary>The logger to use for logging information about function invocation.</summary>
    private readonly ILogger _logger;

    /// <summary>The <see cref="ActivitySource"/> to use for telemetry.</summary>
    /// <remarks>This component does not own the instance and should not dispose it.</remarks>
    private readonly ActivitySource? _activitySource;

    /// <summary>Maximum number of roundtrips allowed to the inner client.</summary>
    private int _maximumIterationsPerRequest = 40; // arbitrary default to prevent runaway execution

    /// <summary>Maximum number of consecutive iterations that are allowed contain at least one exception result. If the limit is exceeded, we rethrow the exception instead of continuing.</summary>
    private int _maximumConsecutiveErrorsPerRequest = 3;

    /// <summary>
    /// Initializes a new instance of the <see cref="FunctionInvokingChatClient"/> class.
    /// </summary>
    /// <param name="innerClient">The underlying <see cref="IChatClient"/>, or the next instance in a chain of clients.</param>
    /// <param name="loggerFactory">An <see cref="ILoggerFactory"/> to use for logging information about function invocation.</param>
    /// <param name="functionInvocationServices">An optional <see cref="IServiceProvider"/> to use for resolving services required by the <see cref="AIFunction"/> instances being invoked.</param>
    public NewFunctionInvokingChatClient(IChatClient innerClient, ILoggerFactory? loggerFactory = null, IServiceProvider? functionInvocationServices = null)
        : base(innerClient)
    {
        _logger = (ILogger?)loggerFactory?.CreateLogger<FunctionInvokingChatClient>() ?? NullLogger.Instance;
        _activitySource = innerClient.GetService<ActivitySource>();
        FunctionInvocationServices = functionInvocationServices;
    }

    /// <summary>
    /// Gets or sets the <see cref="FunctionInvocationContext"/> for the current function invocation.
    /// </summary>
    /// <remarks>
    /// This value flows across async calls.
    /// </remarks>
    public static FunctionInvocationContext? CurrentContext
    {
        get => _currentContext.Value;
        protected set => _currentContext.Value = value;
    }

    /// <summary>
    /// Gets or sets a value indicating whether detailed exception information should be included
    /// in the chat history when calling the underlying <see cref="IChatClient"/>.
    /// </summary>
    /// <value>
    /// <see langword="true"/> if the full exception message is added to the chat history
    /// when calling the underlying <see cref="IChatClient"/>.
    /// <see langword="false"/> if a generic error message is included in the chat history.
    /// The default value is <see langword="false"/>.
    /// </value>
    /// <remarks>
    /// <para>
    /// Setting the value to <see langword="false"/> prevents the underlying language model from disclosing
    /// raw exception details to the end user, since it doesn't receive that information. Even in this
    /// case, the raw <see cref="Exception"/> object is available to application code by inspecting
    /// the <see cref="FunctionResultContent.Exception"/> property.
    /// </para>
    /// <para>
    /// Setting the value to <see langword="true"/> can help the underlying <see cref="IChatClient"/> bypass problems on
    /// its own, for example by retrying the function call with different arguments. However it might
    /// result in disclosing the raw exception information to external users, which can be a security
    /// concern depending on the application scenario.
    /// </para>
    /// <para>
    /// Changing the value of this property while the client is in use might result in inconsistencies
    /// as to whether detailed errors are provided during an in-flight request.
    /// </para>
    /// </remarks>
    public bool IncludeDetailedErrors { get; set; }

    /// <summary>
    /// Gets or sets a value indicating whether to allow concurrent invocation of functions.
    /// </summary>
    /// <value>
    /// <see langword="true"/> if multiple function calls can execute in parallel.
    /// <see langword="false"/> if function calls are processed serially.
    /// The default value is <see langword="false"/>.
    /// </value>
    /// <remarks>
    /// An individual response from the inner client might contain multiple function call requests.
    /// By default, such function calls are processed serially. Set <see cref="AllowConcurrentInvocation"/> to
    /// <see langword="true"/> to enable concurrent invocation such that multiple function calls can execute in parallel.
    /// </remarks>
    public bool AllowConcurrentInvocation { get; set; }

    /// <summary>
    /// Gets or sets the maximum number of iterations per request.
    /// </summary>
    /// <value>
    /// The maximum number of iterations per request.
    /// The default value is 40.
    /// </value>
    /// <remarks>
    /// <para>
    /// Each request to this <see cref="FunctionInvokingChatClient"/> might end up making
    /// multiple requests to the inner client. Each time the inner client responds with
    /// a function call request, this client might perform that invocation and send the results
    /// back to the inner client in a new request. This property limits the number of times
    /// such a roundtrip is performed. The value must be at least one, as it includes the initial request.
    /// </para>
    /// <para>
    /// Changing the value of this property while the client is in use might result in inconsistencies
    /// as to how many iterations are allowed for an in-flight request.
    /// </para>
    /// </remarks>
    public int MaximumIterationsPerRequest
    {
        get => _maximumIterationsPerRequest;
        set
        {
            if (value < 1)
            {
                Throw.ArgumentOutOfRangeException(nameof(value));
            }

            _maximumIterationsPerRequest = value;
        }
    }

    /// <summary>
    /// Gets or sets the maximum number of consecutive iterations that are allowed to fail with an error.
    /// </summary>
    /// <value>
    /// The maximum number of consecutive iterations that are allowed to fail with an error.
    /// The default value is 3.
    /// </value>
    /// <remarks>
    /// <para>
    /// When function invocations fail with an exception, the <see cref="FunctionInvokingChatClient"/>
    /// continues to make requests to the inner client, optionally supplying exception information (as
    /// controlled by <see cref="IncludeDetailedErrors"/>). This allows the <see cref="IChatClient"/> to
    /// recover from errors by trying other function parameters that may succeed.
    /// </para>
    /// <para>
    /// However, in case function invocations continue to produce exceptions, this property can be used to
    /// limit the number of consecutive failing attempts. When the limit is reached, the exception will be
    /// rethrown to the caller.
    /// </para>
    /// <para>
    /// If the value is set to zero, all function calling exceptions immediately terminate the function
    /// invocation loop and the exception will be rethrown to the caller.
    /// </para>
    /// <para>
    /// Changing the value of this property while the client is in use might result in inconsistencies
    /// as to how many iterations are allowed for an in-flight request.
    /// </para>
    /// </remarks>
    public int MaximumConsecutiveErrorsPerRequest
    {
        get => _maximumConsecutiveErrorsPerRequest;
        set => _maximumConsecutiveErrorsPerRequest = Throw.IfLessThan(value, 0);
    }

    /// <summary>Gets or sets a collection of additional tools the client is able to invoke.</summary>
    /// <remarks>
    /// These will not impact the requests sent by the <see cref="FunctionInvokingChatClient"/>, which will pass through the
    /// <see cref="ChatOptions.Tools" /> unmodified. However, if the inner client requests the invocation of a tool
    /// that was not in <see cref="ChatOptions.Tools" />, this <see cref="AdditionalTools"/> collection will also be consulted
    /// to look for a corresponding tool to invoke. This is useful when the service may have been pre-configured to be aware
    /// of certain tools that aren't also sent on each individual request.
    /// </remarks>
    public IList<AITool>? AdditionalTools { get; set; }

    /// <summary>Gets or sets a delegate used to invoke <see cref="AIFunction"/> instances.</summary>
    /// <remarks>
    /// By default, the protected <see cref="InvokeFunctionAsync"/> method is called for each <see cref="AIFunction"/> to be invoked,
    /// invoking the instance and returning its result. If this delegate is set to a non-<see langword="null"/> value,
    /// <see cref="InvokeFunctionAsync"/> will replace its normal invocation with a call to this delegate, enabling
    /// this delegate to assume all invocation handling of the function.
    /// </remarks>
    public Func<FunctionInvocationContext, CancellationToken, ValueTask<object?>>? FunctionInvoker { get; set; }

    /// <inheritdoc/>
    public override async Task<ChatResponse> GetResponseAsync(
        IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(messages);

        // A single request into this GetResponseAsync may result in multiple requests to the inner client.
        // Create an activity to group them together for better observability.
        using Activity? activity = _activitySource?.StartActivity($"{nameof(FunctionInvokingChatClient)}.{nameof(GetResponseAsync)}");

        // Copy the original messages in order to avoid enumerating the original messages multiple times.
        // The IEnumerable can represent an arbitrary amount of work.
        List<ChatMessage> originalMessages = [.. messages];
        messages = originalMessages;

        List<ChatMessage>? augmentedHistory = null; // the actual history of messages sent on turns other than the first
        ChatResponse? response = null; // the response from the inner client, which is possibly modified and then eventually returned
        List<ChatMessage>? responseMessages = null; // tracked list of messages, across multiple turns, to be used for the final response
        UsageDetails? totalUsage = null; // tracked usage across all turns, to be used for the final response
        List<FunctionCallContent>? functionCallContents = null; // function call contents that need responding to in the current turn
        bool lastIterationHadConversationId = false; // whether the last iteration's response had a ConversationId set
        int consecutiveErrorCount = 0;

        // Process approval requests (remove from originalMessages) and rejected approval responses (re-create FCC and create failed FRC).
        var (preDownstreamCallHistory, notInvokedApprovals) = ProcessFunctionApprovalResponses(originalMessages, !string.IsNullOrWhiteSpace(options?.ConversationId), toolResponseId: null, functionCallContentFallbackMessageId: null);

        // Invoke approved approval responses, which generates some additional FRC wrapped in ChatMessage.
        (IList<ChatMessage>? invokedApprovedFunctionApprovalResponses, bool shouldTerminate, consecutiveErrorCount) =
            await InvokeApprovedFunctionApprovalResponses(notInvokedApprovals, originalMessages, options, consecutiveErrorCount, isStreaming: false, cancellationToken);

        if (invokedApprovedFunctionApprovalResponses is not null)
        {
            // We need to add the generated FRC to the list we'll return to callers as part of the next response.
            preDownstreamCallHistory ??= [];
            preDownstreamCallHistory.AddRange(invokedApprovedFunctionApprovalResponses);
        }

        if (shouldTerminate)
        {
            return new ChatResponse(preDownstreamCallHistory);
        }

        for (int iteration = 0; ; iteration++)
        {
            functionCallContents?.Clear();

            // Make the call to the inner client.
            response = await base.GetResponseAsync(messages, options, cancellationToken);
            if (response is null)
            {
                Throw.InvalidOperationException($"The inner {nameof(IChatClient)} returned a null {nameof(ChatResponse)}.");
            }

            // Before we do any function execution, make sure that any functions that require approval, have been turned into approval requests
            // so that they don't get executed here.
            response.Messages = await ReplaceFunctionCallsWithApprovalRequests(response.Messages, options?.Tools, AdditionalTools);

            // Any function call work to do? If yes, ensure we're tracking that work in functionCallContents.
            bool requiresFunctionInvocation =
                (options?.Tools is { Count: > 0 } || AdditionalTools is { Count: > 0 }) &&
                iteration < MaximumIterationsPerRequest &&
                CopyFunctionCalls(response.Messages, ref functionCallContents);

            // In a common case where we make a request and there's no function calling work required,
            // fast path out by just returning the original response.
            if (iteration == 0 && !requiresFunctionInvocation)
            {
                // Insert any pre-invocation FCC and FRC that were converted from approval responses into the response here,
                // so they are returned to the caller.
                response.Messages = UpdateResponseMessagesWithPreDownstreamCallHistory(response.Messages, preDownstreamCallHistory);
                preDownstreamCallHistory = null;

                return response;
            }

            // Track aggregate details from the response, including all of the response messages and usage details.
            (responseMessages ??= []).AddRange(response.Messages);
            if (response.Usage is not null)
            {
                if (totalUsage is not null)
                {
                    totalUsage.Add(response.Usage);
                }
                else
                {
                    totalUsage = response.Usage;
                }
            }

            // If there are no tools to call, or for any other reason we should stop, we're done.
            // Break out of the loop and allow the handling at the end to configure the response
            // with aggregated data from previous requests.
            if (!requiresFunctionInvocation)
            {
                break;
            }

            // Prepare the history for the next iteration.
            FixupHistories(originalMessages, ref messages, ref augmentedHistory, response, responseMessages, ref lastIterationHadConversationId);

            // Add the responses from the function calls into the augmented history and also into the tracked
            // list of response messages.
            var modeAndMessages = await ProcessFunctionCallsAsync(augmentedHistory, options, functionCallContents!, iteration, consecutiveErrorCount, isStreaming: false, cancellationToken);
            responseMessages.AddRange(modeAndMessages.MessagesAdded);
            consecutiveErrorCount = modeAndMessages.NewConsecutiveErrorCount;

            if (modeAndMessages.ShouldTerminate)
            {
                break;
            }

            UpdateOptionsForNextIteration(ref options, response.ConversationId);
        }

        Debug.Assert(responseMessages is not null, "Expected to only be here if we have response messages.");
        response.Messages = responseMessages!;
        response.Usage = totalUsage;

        AddUsageTags(activity, totalUsage);

        return response;
    }

    /// <inheritdoc/>
    public override async IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(
        IEnumerable<ChatMessage> messages, ChatOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(messages);

        // A single request into this GetStreamingResponseAsync may result in multiple requests to the inner client.
        // Create an activity to group them together for better observability.
        using Activity? activity = _activitySource?.StartActivity($"{nameof(FunctionInvokingChatClient)}.{nameof(GetStreamingResponseAsync)}");
        UsageDetails? totalUsage = activity is { IsAllDataRequested: true } ? new() : null; // tracked usage across all turns, to be used for activity purposes

        // Copy the original messages in order to avoid enumerating the original messages multiple times.
        // The IEnumerable can represent an arbitrary amount of work.
        List<ChatMessage> originalMessages = [.. messages];
        messages = originalMessages;

        List<ChatMessage>? augmentedHistory = null; // the actual history of messages sent on turns other than the first
        List<FunctionCallContent>? functionCallContents = null; // function call contents that need responding to in the current turn
        List<ChatMessage>? responseMessages = null; // tracked list of messages, across multiple turns, to be used in fallback cases to reconstitute history
        bool lastIterationHadConversationId = false; // whether the last iteration's response had a ConversationId set
        List<ChatResponseUpdate> updates = []; // updates from the current response
        int consecutiveErrorCount = 0;

        // This is a synthetic ID since we're generating the tool messages instead of getting them from
        // the underlying provider. When emitting the streamed chunks, it's perfectly valid for us to
        // use the same message ID for all of them within a given iteration, as this is a single logical
        // message with multiple content items. We could also use different message IDs per tool content,
        // but there's no benefit to doing so.
        string toolResponseId = Guid.NewGuid().ToString("N");

        // We also need a synthetic ID for the function call content for approved function calls
        // where we don't know what the original message id of the function call was.
        string functionCallContentFallbackMessageId = Guid.NewGuid().ToString("N");

        ApprovalRequiredAIFunction[]? approvalRequiredFunctions = (options?.Tools ?? []).Concat(AdditionalTools ?? []).OfType<ApprovalRequiredAIFunction>().ToArray();
        bool hasApprovalRequiringFunctions = approvalRequiredFunctions.Length > 0;

        // Process approval requests (remove from original messages) and rejected approval responses (re-create FCC and create failed FRC).
        var (preDownstreamCallHistory, notInvokedApprovals) = ProcessFunctionApprovalResponses(originalMessages, !string.IsNullOrWhiteSpace(options?.ConversationId), toolResponseId, functionCallContentFallbackMessageId);
        if (preDownstreamCallHistory is not null)
        {
            foreach (var message in preDownstreamCallHistory)
            {
                yield return ConvertToolResultMessageToUpdate(message, options?.ConversationId, message.MessageId);
                Activity.Current = activity; // workaround for https://github.com/dotnet/runtime/issues/47802
            }
        }

        // Invoke approved approval responses, which generates some additional FRC wrapped in ChatMessage.
        (IList<ChatMessage>? invokedApprovedFunctionApprovalResponses, bool shouldTerminate, consecutiveErrorCount) =
            await InvokeApprovedFunctionApprovalResponses(notInvokedApprovals, originalMessages, options, consecutiveErrorCount, isStreaming: true, cancellationToken);

        if (invokedApprovedFunctionApprovalResponses is not null)
        {
            foreach (var message in invokedApprovedFunctionApprovalResponses)
            {
                message.MessageId = toolResponseId;
                yield return ConvertToolResultMessageToUpdate(message, options?.ConversationId, message.MessageId);
                Activity.Current = activity; // workaround for https://github.com/dotnet/runtime/issues/47802
            }

            if (shouldTerminate)
            {
                yield break;
            }
        }

        for (int iteration = 0; ; iteration++)
        {
            updates.Clear();
            functionCallContents?.Clear();

            bool hasApprovalRequiringFcc = false;
            int lastApprovalCheckedFCCIndex = 0;
            int lastYieldedUpdateIndex = 0;

            await foreach (var update in base.GetStreamingResponseAsync(messages, options, cancellationToken))
            {
                if (update is null)
                {
                    Throw.InvalidOperationException($"The inner {nameof(IChatClient)} streamed a null {nameof(ChatResponseUpdate)}.");
                }

                updates.Add(update);

                _ = CopyFunctionCalls(update.Contents, ref functionCallContents);

                if (totalUsage is not null)
                {
                    IList<AIContent> contents = update.Contents;
                    int contentsCount = contents.Count;
                    for (int i = 0; i < contentsCount; i++)
                    {
                        if (contents[i] is UsageContent uc)
                        {
                            totalUsage.Add(uc.Details);
                        }
                    }
                }

                if (functionCallContents?.Count is not > 0 || !hasApprovalRequiringFunctions)
                {
                    // If there are no function calls to make yet, or if none of the functions require approval at all,
                    // we can yield the update as-is.
                    lastYieldedUpdateIndex++;
                    yield return update;
                    Activity.Current = activity; // workaround for https://github.com/dotnet/runtime/issues/47802
                }
                else
                {
                    // Check if any of the function call contents in this update requires approval.
                    // Once we find the first one that requires approval, this method becomes a no-op.
                    (hasApprovalRequiringFcc, lastApprovalCheckedFCCIndex) = await CheckForApprovalRequiringFCCAsync(
                        functionCallContents, approvalRequiredFunctions, hasApprovalRequiringFcc, lastApprovalCheckedFCCIndex);

                    // We've encountered a function call content that requires approval (either in this update or ealier)
                    // so we need to ask for approval for all functions, since we cannot mix and match.
                    if (hasApprovalRequiringFcc)
                    {
                        // Convert all function call contents into approval requests from the last yielded update index
                        // and yield all those updates.
                        for (; lastYieldedUpdateIndex < updates.Count; lastYieldedUpdateIndex++)
                        {
                            var updateToYield = updates[lastYieldedUpdateIndex];
                            if (TryReplaceFunctionCallsWithApprovalRequests(updateToYield.Contents, out var updatedContents))
                            {
                                updateToYield.Contents = updatedContents;
                            }
                            yield return updateToYield;
                            Activity.Current = activity; // workaround for https://github.com/dotnet/runtime/issues/47802
                        }
                    }
                    else
                    {
                        // We don't have any appoval requiring function calls yet, but we may receive some in future
                        // so we cannot yield the updates yet. We'll just keep them in the updates list
                        // for later.
                        // We will yield the updates as soon as we receive a function call content that requires approval or
                        // when we reach the end of the updates stream.
                    }
                }

                Activity.Current = activity; // workaround for https://github.com/dotnet/runtime/issues/47802
            }

            // If there are no tools to call, or for any other reason we should stop, return the response.
            if (functionCallContents is not { Count: > 0 } ||
                hasApprovalRequiringFcc ||
                (options?.Tools is not { Count: > 0 } && AdditionalTools is not { Count: > 0 }) ||
                iteration >= _maximumIterationsPerRequest)
            {
                break;
            }

            // Reconstitute a response from the response updates.
            var response = updates.ToChatResponse();
            (responseMessages ??= []).AddRange(response.Messages);

            // Prepare the history for the next iteration.
            FixupHistories(originalMessages, ref messages, ref augmentedHistory, response, responseMessages, ref lastIterationHadConversationId);

            // Process all of the functions, adding their results into the history.
            var modeAndMessages = await ProcessFunctionCallsAsync(augmentedHistory, options, functionCallContents, iteration, consecutiveErrorCount, isStreaming: true, cancellationToken);
            responseMessages.AddRange(modeAndMessages.MessagesAdded);
            consecutiveErrorCount = modeAndMessages.NewConsecutiveErrorCount;

            // Stream any generated function results. This mirrors what's done for GetResponseAsync, where the returned messages
            // includes all activities, including generated function results.
            foreach (var message in modeAndMessages.MessagesAdded)
            {
                yield return ConvertToolResultMessageToUpdate(message, response.ConversationId, toolResponseId);
                Activity.Current = activity; // workaround for https://github.com/dotnet/runtime/issues/47802
            }

            if (modeAndMessages.ShouldTerminate)
            {
                break;
            }

            UpdateOptionsForNextIteration(ref options, response.ConversationId);
        }

        AddUsageTags(activity, totalUsage);
    }

    /// <summary>Adds tags to <paramref name="activity"/> for usage details in <paramref name="usage"/>.</summary>
    private static void AddUsageTags(Activity? activity, UsageDetails? usage)
    {
        if (usage is not null && activity is { IsAllDataRequested: true })
        {
            if (usage.InputTokenCount is long inputTokens)
            {
                _ = activity.AddTag(OpenTelemetryConsts.GenAI.Usage.InputTokens, (int)inputTokens);
            }

            if (usage.OutputTokenCount is long outputTokens)
            {
                _ = activity.AddTag(OpenTelemetryConsts.GenAI.Usage.OutputTokens, (int)outputTokens);
            }
        }
    }

    /// <summary>Prepares the various chat message lists after a response from the inner client and before invoking functions.</summary>
    /// <param name="originalMessages">The original messages provided by the caller.</param>
    /// <param name="messages">The messages reference passed to the inner client.</param>
    /// <param name="augmentedHistory">The augmented history containing all the messages to be sent.</param>
    /// <param name="response">The most recent response being handled.</param>
    /// <param name="allTurnsResponseMessages">A list of all response messages received up until this point.</param>
    /// <param name="lastIterationHadConversationId">Whether the previous iteration's response had a conversation ID.</param>
    private static void FixupHistories(
        IEnumerable<ChatMessage> originalMessages,
        ref IEnumerable<ChatMessage> messages,
        [NotNull] ref List<ChatMessage>? augmentedHistory,
        ChatResponse response,
        List<ChatMessage> allTurnsResponseMessages,
        ref bool lastIterationHadConversationId)
    {
        // We're now going to need to augment the history with function result contents.
        // That means we need a separate list to store the augmented history.
        if (response.ConversationId is not null)
        {
            // The response indicates the inner client is tracking the history, so we don't want to send
            // anything we've already sent or received.
            if (augmentedHistory is not null)
            {
                augmentedHistory.Clear();
            }
            else
            {
                augmentedHistory = [];
            }

            lastIterationHadConversationId = true;
        }
        else if (lastIterationHadConversationId)
        {
            // In the very rare case where the inner client returned a response with a conversation ID but then
            // returned a subsequent response without one, we want to reconstitute the full history. To do that,
            // we can populate the history with the original chat messages and then all of the response
            // messages up until this point, which includes the most recent ones.
            augmentedHistory ??= [];
            augmentedHistory.Clear();
            augmentedHistory.AddRange(originalMessages);
            augmentedHistory.AddRange(allTurnsResponseMessages);

            lastIterationHadConversationId = false;
        }
        else
        {
            // If augmentedHistory is already non-null, then we've already populated it with everything up
            // until this point (except for the most recent response). If it's null, we need to seed it with
            // the chat history provided by the caller.
            augmentedHistory ??= originalMessages.ToList();

            // Now add the most recent response messages.
            augmentedHistory.AddMessages(response);

            lastIterationHadConversationId = false;
        }

        // Use the augmented history as the new set of messages to send.
        messages = augmentedHistory;
    }

    /// <summary>Copies any <see cref="FunctionCallContent"/> from <paramref name="messages"/> to <paramref name="functionCalls"/>.</summary>
    private static bool CopyFunctionCalls(
        IList<ChatMessage> messages, [NotNullWhen(true)] ref List<FunctionCallContent>? functionCalls)
    {
        bool any = false;
        int count = messages.Count;
        for (int i = 0; i < count; i++)
        {
            any |= CopyFunctionCalls(messages[i].Contents, ref functionCalls);
        }

        return any;
    }

    /// <summary>Copies any <see cref="FunctionCallContent"/> from <paramref name="content"/> to <paramref name="functionCalls"/>.</summary>
    private static bool CopyFunctionCalls(
        IList<AIContent> content, [NotNullWhen(true)] ref List<FunctionCallContent>? functionCalls)
    {
        bool any = false;
        int count = content.Count;
        for (int i = 0; i < count; i++)
        {
            if (content[i] is FunctionCallContent functionCall)
            {
                (functionCalls ??= []).Add(functionCall);
                any = true;
            }
        }

        return any;
    }

    private static void UpdateOptionsForNextIteration(ref ChatOptions? options, string? conversationId)
    {
        if (options is null)
        {
            if (conversationId is not null)
            {
                options = new() { ConversationId = conversationId };
            }
        }
        else if (options.ToolMode is RequiredChatToolMode)
        {
            // We have to reset the tool mode to be non-required after the first iteration,
            // as otherwise we'll be in an infinite loop.
            options = options.Clone();
            options.ToolMode = null;
            options.ConversationId = conversationId;
        }
        else if (options.ConversationId != conversationId)
        {
            // As with the other modes, ensure we've propagated the chat conversation ID to the options.
            // We only need to clone the options if we're actually mutating it.
            options = options.Clone();
            options.ConversationId = conversationId;
        }
    }

    /// <summary>
    /// Processes the function calls in the <paramref name="functionCallContents"/> list.
    /// </summary>
    /// <param name="messages">The current chat contents, inclusive of the function call contents being processed.</param>
    /// <param name="options">The options used for the response being processed.</param>
    /// <param name="functionCallContents">The function call contents representing the functions to be invoked.</param>
    /// <param name="iteration">The iteration number of how many roundtrips have been made to the inner client.</param>
    /// <param name="consecutiveErrorCount">The number of consecutive iterations, prior to this one, that were recorded as having function invocation errors.</param>
    /// <param name="isStreaming">Whether the function calls are being processed in a streaming context.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.</param>
    /// <returns>A value indicating how the caller should proceed.</returns>
    private async Task<(bool ShouldTerminate, int NewConsecutiveErrorCount, IList<ChatMessage> MessagesAdded)> ProcessFunctionCallsAsync(
        List<ChatMessage> messages, ChatOptions? options, List<FunctionCallContent> functionCallContents, int iteration, int consecutiveErrorCount,
        bool isStreaming, CancellationToken cancellationToken)
    {
        // We must add a response for every tool call, regardless of whether we successfully executed it or not.
        // If we successfully execute it, we'll add the result. If we don't, we'll add an error.

        Debug.Assert(functionCallContents.Count > 0, "Expected at least one function call.");
        var shouldTerminate = false;
        var captureCurrentIterationExceptions = consecutiveErrorCount < _maximumConsecutiveErrorsPerRequest;

        // Process all functions. If there's more than one and concurrent invocation is enabled, do so in parallel.
        if (functionCallContents.Count == 1)
        {
            FunctionInvocationResult result = await ProcessFunctionCallAsync(
                messages, options, functionCallContents,
                iteration, 0, captureCurrentIterationExceptions, isStreaming, cancellationToken);

            IList<ChatMessage> addedMessages = CreateResponseMessages([result]);
            ThrowIfNoFunctionResultsAdded(addedMessages);
            UpdateConsecutiveErrorCountOrThrow(addedMessages, ref consecutiveErrorCount);
            messages.AddRange(addedMessages);

            return (result.Terminate, consecutiveErrorCount, addedMessages);
        }
        else
        {
            List<FunctionInvocationResult> results = [];

            if (AllowConcurrentInvocation)
            {
                // Rather than awaiting each function before invoking the next, invoke all of them
                // and then await all of them. We avoid forcibly introducing parallelism via Task.Run,
                // but if a function invocation completes asynchronously, its processing can overlap
                // with the processing of other the other invocation invocations.
                results.AddRange(await Task.WhenAll(
                    from callIndex in Enumerable.Range(0, functionCallContents.Count)
                    select ProcessFunctionCallAsync(
                        messages, options, functionCallContents,
                        iteration, callIndex, captureExceptions: true, isStreaming, cancellationToken)));

                shouldTerminate = results.Any(r => r.Terminate);
            }
            else
            {
                // Invoke each function serially.
                for (int callIndex = 0; callIndex < functionCallContents.Count; callIndex++)
                {
                    var functionResult = await ProcessFunctionCallAsync(
                        messages, options, functionCallContents,
                        iteration, callIndex, captureCurrentIterationExceptions, isStreaming, cancellationToken);

                    results.Add(functionResult);

                    // If any function requested termination, we should stop right away.
                    if (functionResult.Terminate)
                    {
                        shouldTerminate = true;
                        break;
                    }
                }
            }

            IList<ChatMessage> addedMessages = CreateResponseMessages(results.ToArray());
            ThrowIfNoFunctionResultsAdded(addedMessages);
            UpdateConsecutiveErrorCountOrThrow(addedMessages, ref consecutiveErrorCount);
            messages.AddRange(addedMessages);

            return (shouldTerminate, consecutiveErrorCount, addedMessages);
        }
    }

#pragma warning disable CA1851 // Possible multiple enumerations of 'IEnumerable' collection
    /// <summary>
    /// Updates the consecutive error count, and throws an exception if the count exceeds the maximum.
    /// </summary>
    /// <param name="added">Added messages.</param>
    /// <param name="consecutiveErrorCount">Consecutive error count.</param>
    /// <exception cref="AggregateException">Thrown if the maximum consecutive error count is exceeded.</exception>
    private void UpdateConsecutiveErrorCountOrThrow(IList<ChatMessage> added, ref int consecutiveErrorCount)
    {
        var allExceptions = added.SelectMany(m => m.Contents.OfType<FunctionResultContent>())
            .Select(frc => frc.Exception!)
            .Where(e => e is not null);

        if (allExceptions.Any())
        {
            consecutiveErrorCount++;
            if (consecutiveErrorCount > _maximumConsecutiveErrorsPerRequest)
            {
                var allExceptionsArray = allExceptions.ToArray();
                if (allExceptionsArray.Length == 1)
                {
                    ExceptionDispatchInfo.Capture(allExceptionsArray[0]).Throw();
                }
                else
                {
                    throw new AggregateException(allExceptionsArray);
                }
            }
        }
        else
        {
            consecutiveErrorCount = 0;
        }
    }
#pragma warning restore CA1851

    /// <summary>
    /// Throws an exception if <see cref="CreateResponseMessages"/> doesn't create any messages.
    /// </summary>
    private void ThrowIfNoFunctionResultsAdded(IList<ChatMessage>? messages)
    {
        if (messages is null || messages.Count == 0)
        {
            Throw.InvalidOperationException($"{GetType().Name}.{nameof(CreateResponseMessages)} returned null or an empty collection of messages.");
        }
    }

    /// <summary>Processes the function call described in <paramref name="callContents"/>[<paramref name="iteration"/>].</summary>
    /// <param name="messages">The current chat contents, inclusive of the function call contents being processed.</param>
    /// <param name="options">The options used for the response being processed.</param>
    /// <param name="callContents">The function call contents representing all the functions being invoked.</param>
    /// <param name="iteration">The iteration number of how many roundtrips have been made to the inner client.</param>
    /// <param name="functionCallIndex">The 0-based index of the function being called out of <paramref name="callContents"/>.</param>
    /// <param name="captureExceptions">If true, handles function-invocation exceptions by returning a value with <see cref="FunctionInvocationStatus.Exception"/>. Otherwise, rethrows.</param>
    /// <param name="isStreaming">Whether the function calls are being processed in a streaming context.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.</param>
    /// <returns>A value indicating how the caller should proceed.</returns>
    private async Task<FunctionInvocationResult> ProcessFunctionCallAsync(
        List<ChatMessage> messages, ChatOptions? options, List<FunctionCallContent> callContents,
        int iteration, int functionCallIndex, bool captureExceptions, bool isStreaming, CancellationToken cancellationToken)
    {
        var callContent = callContents[functionCallIndex];

        // Look up the AIFunction for the function call. If the requested function isn't available, send back an error.
        AIFunction? aiFunction = FindAIFunction(options?.Tools, callContent.Name) ?? FindAIFunction(AdditionalTools, callContent.Name);
        if (aiFunction is null)
        {
            return new(terminate: false, FunctionInvocationStatus.NotFound, callContent, result: null, exception: null);
        }

        FunctionInvocationContext context = new()
        {
            Function = aiFunction,
            Arguments = new(callContent.Arguments) { Services = FunctionInvocationServices },
            Messages = messages,
            Options = options,
            CallContent = callContent,
            Iteration = iteration,
            FunctionCallIndex = functionCallIndex,
            FunctionCount = callContents.Count,
            IsStreaming = isStreaming
        };

        object? result;
        try
        {
            result = await InstrumentedInvokeFunctionAsync(context, cancellationToken);
        }
        catch (Exception e) when (!cancellationToken.IsCancellationRequested)
        {
            if (!captureExceptions)
            {
                throw;
            }

            return new(
                terminate: false,
                FunctionInvocationStatus.Exception,
                callContent,
                result: null,
                exception: e);
        }

        return new(
            terminate: context.Terminate,
            FunctionInvocationStatus.RanToCompletion,
            callContent,
            result,
            exception: null);

        static AIFunction? FindAIFunction(IList<AITool>? tools, string functionName)
        {
            if (tools is not null)
            {
                int count = tools.Count;
                for (int i = 0; i < count; i++)
                {
                    if (tools[i] is AIFunction function && function.Name == functionName)
                    {
                        return function;
                    }
                }
            }

            return null;
        }
    }

    /// <summary>Creates one or more response messages for function invocation results.</summary>
    /// <param name="results">Information about the function call invocations and results.</param>
    /// <returns>A list of all chat messages created from <paramref name="results"/>.</returns>
    protected virtual IList<ChatMessage> CreateResponseMessages(
        ReadOnlySpan<FunctionInvocationResult> results)
    {
        var contents = new List<AIContent>(results.Length);
        for (int i = 0; i < results.Length; i++)
        {
            contents.Add(CreateFunctionResultContent(results[i]));
        }

        return [new(ChatRole.Tool, contents)];

        FunctionResultContent CreateFunctionResultContent(FunctionInvocationResult result)
        {
            _ = Throw.IfNull(result);

            object? functionResult;
            if (result.Status == FunctionInvocationStatus.RanToCompletion)
            {
                functionResult = result.Result ?? "Success: Function completed.";
            }
            else
            {
                string message = result.Status switch
                {
                    FunctionInvocationStatus.NotFound => $"Error: Requested function \"{result.CallContent.Name}\" not found.",
                    FunctionInvocationStatus.Exception => "Error: Function failed.",
                    _ => "Error: Unknown error.",
                };

                if (IncludeDetailedErrors && result.Exception is not null)
                {
                    message = $"{message} Exception: {result.Exception.Message}";
                }

                functionResult = message;
            }

            return new FunctionResultContent(result.CallContent.CallId, functionResult) { Exception = result.Exception };
        }
    }

    /// <summary>Invokes the function asynchronously.</summary>
    /// <param name="context">
    /// The function invocation context detailing the function to be invoked and its arguments along with additional request information.
    /// </param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>The result of the function invocation, or <see langword="null"/> if the function invocation returned <see langword="null"/>.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="context"/> is <see langword="null"/>.</exception>
    private async Task<object?> InstrumentedInvokeFunctionAsync(FunctionInvocationContext context, CancellationToken cancellationToken)
    {
        _ = Throw.IfNull(context);

        using Activity? activity = _activitySource?.StartActivity(
            $"{OpenTelemetryConsts.GenAI.ExecuteTool} {context.Function.Name}",
            ActivityKind.Internal,
            default(ActivityContext),
            [
                new(OpenTelemetryConsts.GenAI.Operation.Name, "execute_tool"),
                new(OpenTelemetryConsts.GenAI.Tool.Call.Id, context.CallContent.CallId),
                new(OpenTelemetryConsts.GenAI.Tool.Name, context.Function.Name),
                new(OpenTelemetryConsts.GenAI.Tool.Description, context.Function.Description),
            ]);

        long startingTimestamp = 0;
        if (_logger.IsEnabled(LogLevel.Debug))
        {
            startingTimestamp = Stopwatch.GetTimestamp();
            if (_logger.IsEnabled(LogLevel.Trace))
            {
                LogInvokingSensitive(context.Function.Name, LoggingHelpers.AsJson(context.Arguments, context.Function.JsonSerializerOptions));
            }
            else
            {
                LogInvoking(context.Function.Name);
            }
        }

        object? result = null;
        try
        {
            CurrentContext = context; // doesn't need to be explicitly reset after, as that's handled automatically at async method exit
            result = await InvokeFunctionAsync(context, cancellationToken);
        }
        catch (Exception e)
        {
            if (activity is not null)
            {
                _ = activity.SetTag("error.type", e.GetType().FullName)
                            .SetStatus(ActivityStatusCode.Error, e.Message);
            }

            if (e is OperationCanceledException)
            {
                LogInvocationCanceled(context.Function.Name);
            }
            else
            {
                LogInvocationFailed(context.Function.Name, e);
            }

            throw;
        }
        finally
        {
            if (_logger.IsEnabled(LogLevel.Debug))
            {
                TimeSpan elapsed = GetElapsedTime(startingTimestamp);

                if (result is not null && _logger.IsEnabled(LogLevel.Trace))
                {
                    LogInvocationCompletedSensitive(context.Function.Name, elapsed, LoggingHelpers.AsJson(result, context.Function.JsonSerializerOptions));
                }
                else
                {
                    LogInvocationCompleted(context.Function.Name, elapsed);
                }
            }
        }

        return result;
    }

    /// <summary>This method will invoke the function within the try block.</summary>
    /// <param name="context">The function invocation context.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>The function result.</returns>
    protected virtual ValueTask<object?> InvokeFunctionAsync(FunctionInvocationContext context, CancellationToken cancellationToken)
    {
        _ = Throw.IfNull(context);

        return FunctionInvoker is { } invoker ?
            invoker(context, cancellationToken) :
            context.Function.InvokeAsync(context.Arguments, cancellationToken);
    }

    /// <summary>
    /// 1. Remove all <see cref="FunctionApprovalRequestContent"/> and <see cref="FunctionApprovalResponseContent"/> from the <paramref name="originalMessages"/>.
    /// 2. Recreate <see cref="FunctionCallContent"/> for any <see cref="FunctionApprovalResponseContent"/> that haven't been executed yet.
    /// 3. Genreate failed <see cref="FunctionResultContent"/> for any rejected <see cref="FunctionApprovalResponseContent"/>.
    /// 4. add all the new content items to <paramref name="originalMessages"/> and return them as the pre-invocation history.
    /// </summary>
    private static (List<ChatMessage>? preDownstreamCallHistory, List<ApprovalResultWithRequestMessage>? approvals) ProcessFunctionApprovalResponses(
        List<ChatMessage> originalMessages, bool hasConversationId, string? toolResponseId, string? functionCallContentFallbackMessageId)
    {
        // Extract any approval responses where we need to execute or reject the function calls.
        // The original messages are also modified to remove all approval requests and responses.
        var notInvokedResponses = ExtractAndRemoveApprovalRequestsAndResponses(originalMessages);

        // Wrap the function call content in message(s).
        ICollection<ChatMessage>? allPreDownstreamCallMessages = ConvertToFunctionCallContentMessages(
            [.. notInvokedResponses.rejections ?? [], .. notInvokedResponses.approvals ?? []], functionCallContentFallbackMessageId);

        // Generate failed function result contents for any rejected requests and wrap it in a message.
        List<AIContent>? rejectedFunctionCallResults = GenerateRejectedFunctionResults(notInvokedResponses.rejections, toolResponseId);
        ChatMessage? rejectedPreDownstreamCallResultsMessage = rejectedFunctionCallResults != null ?
            new ChatMessage(ChatRole.Tool, rejectedFunctionCallResults) { MessageId = toolResponseId } :
            null;

        // Add all the FCC that we generated to the pre-downstream-call history so that they can be returned to the caller as part of the next response.
        // Also, if we are not dealing with a service thread (i.e. we don't have a conversation ID), add them
        // into the original messages list so that they are passed to the inner client and can be used to generate a result.
        List<ChatMessage>? preDownstreamCallHistory = null;
        if (allPreDownstreamCallMessages is not null)
        {
            preDownstreamCallHistory ??= [];
            foreach (var message in allPreDownstreamCallMessages)
            {
                preDownstreamCallHistory.Add(message);
                if (!hasConversationId)
                {
                    originalMessages.Add(message);
                }
            }
        }

        // Add all the FRC that we generated to the pre-downstream-call history so that they can be returned to the caller as part of the next response.
        // Also, add them into the original messages list so that they are passed to the inner client and can be used to generate a result.
        if (rejectedPreDownstreamCallResultsMessage is not null)
        {
            preDownstreamCallHistory ??= [];
            originalMessages.Add(rejectedPreDownstreamCallResultsMessage);
            preDownstreamCallHistory.Add(rejectedPreDownstreamCallResultsMessage);
        }

        return (preDownstreamCallHistory, notInvokedResponses.approvals);
    }

    /// <summary>
    /// Execute the provided <see cref="FunctionApprovalResponseContent"/> and return the resulting <see cref="FunctionCallContent"/>.
    /// </summary>
    private async Task<(IList<ChatMessage>? FunctionResultContent, bool ShouldTerminate, int ConsecutiveErrorCount)> InvokeApprovedFunctionApprovalResponses(
        List<ApprovalResultWithRequestMessage>? notInvokedApprovals, List<ChatMessage> originalMessages, ChatOptions? options, int consecutiveErrorCount, bool isStreaming, CancellationToken cancellationToken)
    {
        // Check if there are any function calls to do for any approved functions and execute them.
        if (notInvokedApprovals is { Count: > 0 })
        {
            // The FRC that is generated here is already added to originalMessages by ProcessFunctionCallsAsync.
            var modeAndMessages = await ProcessFunctionCallsAsync(originalMessages, options, notInvokedApprovals.Select(x => x.Response.FunctionCall).ToList(), 0, consecutiveErrorCount, isStreaming, cancellationToken);
            consecutiveErrorCount = modeAndMessages.NewConsecutiveErrorCount;

            return (modeAndMessages.MessagesAdded, modeAndMessages.ShouldTerminate, consecutiveErrorCount);
        }

        return (null, false, consecutiveErrorCount);
    }

    /// <summary>
    /// This method extracts the approval requests and responses from the provided list of messages, validates them, filters them to ones that require execution and splits them into approved and rejected.
    /// </summary>
    /// <remarks>
    /// 1st iteration: over all messages and content
    /// =====
    /// Build a list of all function call ids that are already executed.
    /// Build a list of all function approval requests and responses.
    /// Build a list of the content we want to keep (everything except approval requests and responses) and create a new list of messages for those.
    /// Validate that we have an approval response for each approval request.
    ///
    /// 2nd iteration: over all approval responses
    /// =====
    /// Filter out any approval responses that already have a matching function result (i.e. already executed).
    /// Find the matching function approval request for any response (where available).
    /// Split the approval responses into two lists: approved and rejected, with their request messages (where available).
    ///
    /// We return the messages containing the approval requests since these are the same messages that originally contained the FunctionCallContent from the downstream service.
    /// We can then use the metadata from these messages when we re-create the FunctionCallContent messages/updates to return to the caller. This way, when we finally do return
    /// the FuncionCallContent to users it's part of a message/update that contains the same metadata as originally returned to the downstream service.
    /// </remarks>
    private static (List<ApprovalResultWithRequestMessage>? approvals, List<ApprovalResultWithRequestMessage>? rejections) ExtractAndRemoveApprovalRequestsAndResponses(List<ChatMessage> messages)
    {
        Dictionary<string, ChatMessage>? allApprovalRequestsMessages = null;
        List<FunctionApprovalResponseContent>? allApprovalResponses = null;
        HashSet<string>? approvalRequestCallIds = null;
        HashSet<string>? functionResultCallIds = null;

        for (int i = 0; i < messages.Count; i++)
        {
            var message = messages[i];

            List<AIContent>? keptContents = null;

            // Find contents we want to keep.
            for (int j = 0; j < message.Contents.Count; j++)
            {
                var content = message.Contents[j];

                // Maintain a list of function calls that have already been executed, so we can avoid executing them a second time.
                if (content is FunctionResultContent functionResultContent)
                {
                    functionResultCallIds ??= [];
                    functionResultCallIds.Add(functionResultContent.CallId);
                }

                // Validation: Capture each call id for each approval request so that we can ensure that we have a matching response later.
                if (content is FunctionApprovalRequestContent request_)
                {
                    approvalRequestCallIds ??= [];
                    approvalRequestCallIds.Add(request_.FunctionCall.CallId);
                }

                // Validation: Remove the call id for each approval response, to check it off the list of requests we need responses for.
                if (content is FunctionApprovalResponseContent response_ && approvalRequestCallIds is not null)
                {
                    approvalRequestCallIds.Remove(response_.FunctionCall.CallId);
                }

                // Build the list of requets and responses and keep them out of the updated message list
                // since they will be handled in this class, and don't need to be passed further down the stack.
                if (content is FunctionApprovalRequestContent approvalRequest)
                {
                    allApprovalRequestsMessages ??= new Dictionary<string, ChatMessage>();
                    allApprovalRequestsMessages.Add(approvalRequest.Id, message);
                    continue;
                }

                if (content is FunctionApprovalResponseContent approvalResponse)
                {
                    allApprovalResponses ??= [];
                    allApprovalResponses.Add(approvalResponse);
                    continue;
                }

                // If we get to here, we should have just the contents that we want to keep.
                keptContents ??= [];
                keptContents.Add(content);
            }

            if (message.Contents.Count > 0 && keptContents?.Count != message.Contents.Count)
            {
                if (keptContents is null || keptContents.Count == 0)
                {
                    // If we have no contents left after filtering, we can remove the message.
                    messages.RemoveAt(i);
                    i--; // Adjust index since we removed an item.
                    continue;
                }

                // If we have any contents left after filtering, we can keep the message with the new remaining content.
                var newMessage = message.Clone();
                newMessage.Contents = keptContents;
                messages[i] = newMessage;
            }
        }

        // Validation: If we got an approval for each request, we should have no call ids left.
        if (approvalRequestCallIds?.Count is > 0)
        {
            Throw.InvalidOperationException($"FunctionApprovalRequestContent found with FunctionCall.CallId(s) '{string.Join(", ", approvalRequestCallIds)}' that have no matching FunctionApprovalResponseContent.");
        }

        List<ApprovalResultWithRequestMessage>? approvedFunctionCalls = null;
        List<ApprovalResultWithRequestMessage>? rejectedFunctionCalls = null;

        for (int i = 0; i < (allApprovalResponses?.Count ?? 0); i++)
        {
            var approvalResponse = allApprovalResponses![i];

            // Skip any approval responses that have already been executed.
            if (functionResultCallIds?.Contains(approvalResponse.FunctionCall.CallId) is not true)
            {
                ChatMessage? requestMessage = null;
                allApprovalRequestsMessages?.TryGetValue(approvalResponse.FunctionCall.CallId, out requestMessage);

                // Split the responses into approved and rejected.
                if (approvalResponse.Approved)
                {
                    approvedFunctionCalls ??= [];
                    approvedFunctionCalls.Add(new ApprovalResultWithRequestMessage { Response = approvalResponse, RequestMessage = requestMessage });
                }
                else
                {
                    rejectedFunctionCalls ??= [];
                    rejectedFunctionCalls.Add(new ApprovalResultWithRequestMessage { Response = approvalResponse, RequestMessage = requestMessage });
                }
            }
        }

        return (approvedFunctionCalls, rejectedFunctionCalls);
    }

    /// <summary>
    /// If we have any rejected approval responses, we need to generate failed function results for them.
    /// </summary>
    /// <param name="rejections">Any rejected approval responses.</param>
    /// <param name="toolResponseId">The message id to use for the tool response.</param>
    /// <returns>The <see cref="AIContent"/> for the rejected function calls.</returns>
    private static List<AIContent>? GenerateRejectedFunctionResults(
        List<ApprovalResultWithRequestMessage>? rejections,
        string? toolResponseId)
    {
        List<AIContent>? functionResultContent = null;

        if (rejections is { Count: > 0 })
        {
            functionResultContent = [];

            foreach (var rejectedCall in rejections)
            {
                // Create a FunctionResultContent for the rejected function call.
                var functionResult = new FunctionResultContent(rejectedCall.Response.FunctionCall.CallId, "Error: Function invocation approval was not granted.");
                functionResultContent.Add(functionResult);
            }
        }

        return functionResultContent;
    }

    /// <summary>
    /// Extracts the <see cref="FunctionCallContent"/> from the provided <see cref="FunctionApprovalResponseContent"/> to recreate the original function call messages.
    /// The output messages tries to mimic the original messages that contained the <see cref="FunctionCallContent"/>, e.g. if the <see cref="FunctionCallContent"/> had been split into separate messages,
    /// this method will recreate similarly split messages, each with their own <see cref="FunctionCallContent"/>.
    /// </summary>
#pragma warning disable CA1859 // Use concrete types when possible for improved performance
    private static ICollection<ChatMessage>? ConvertToFunctionCallContentMessages(IEnumerable<ApprovalResultWithRequestMessage>? resultWithRequestMessages, string? fallbackMessageId)
#pragma warning restore CA1859 // Use concrete types when possible for improved performance
    {
        if (resultWithRequestMessages is not null)
        {
            ChatMessage? currentMessage = null;
            Dictionary<string, ChatMessage>? messagesById = null;

            foreach (var resultWithRequestMessage in resultWithRequestMessages)
            {
                if (currentMessage is not null && messagesById is null // Don't need to create a dictionary on the first iteration or if we alrady have one.
                    && !(resultWithRequestMessage.RequestMessage is null && currentMessage.MessageId == fallbackMessageId) // Everywhere we have no RequestMessage we use the fallbackMessageId, so in this case there is only one message.
                    && (resultWithRequestMessage.RequestMessage is not null && currentMessage.MessageId != resultWithRequestMessage.RequestMessage?.MessageId)) // Where we do have a RequestMessage, we can check if its message id differs from the current one.
                {
                    // The majority of the time, all FCC would be part of a single message, so no need to create a dictionary for this case.
                    // If we are dealing with multiple messages though, we need to keep track of them by their message ID.
                    messagesById ??= new();
                    messagesById[currentMessage.MessageId ?? string.Empty] = currentMessage;
                }

                if (messagesById is not null)
                {
                    messagesById.TryGetValue(resultWithRequestMessage.RequestMessage?.MessageId ?? string.Empty, out currentMessage);
                }

                if (currentMessage is null)
                {
                    currentMessage = ConvertToFunctionCallContentMessage(resultWithRequestMessage, fallbackMessageId);
                }
                else
                {
                    currentMessage.Contents.Add(resultWithRequestMessage.Response.FunctionCall);
                }

                if (messagesById is not null)
                {
                    messagesById[currentMessage.MessageId ?? string.Empty] = currentMessage;
                }
            }

            return messagesById?.Values as ICollection<ChatMessage> ?? (currentMessage != null ? [currentMessage!] : null);
        }

        return null;
    }

    /// <summary>
    /// Takes the <see cref="FunctionCallContent"/> from the <paramref name="resultWithRequestMessage"/> and wraps it in a <see cref="ChatMessage"/>
    /// using the same message id that the <see cref="FunctionCallContent"/> was originally returned with from the downstream <see cref="IChatClient"/>.
    /// </summary>
    private static ChatMessage ConvertToFunctionCallContentMessage(ApprovalResultWithRequestMessage resultWithRequestMessage, string? fallbackMessageId)
    {
        if (resultWithRequestMessage.RequestMessage is not null)
        {
            var functionCallMessage = resultWithRequestMessage.RequestMessage.Clone();
            functionCallMessage.Contents = [resultWithRequestMessage.Response.FunctionCall];
            functionCallMessage.MessageId ??= fallbackMessageId;
            return functionCallMessage;
        }

        return new ChatMessage(ChatRole.Assistant, [resultWithRequestMessage.Response.FunctionCall]) { MessageId = fallbackMessageId };
    }

    /// <summary>
    /// Check if any of the provided <paramref name="functionCallContents"/> require approval.
    /// Supports checking from a provided index up to the end of the list, to allow efficient incremental checking
    /// when streaming.
    /// </summary>
    private static async Task<(bool hasApprovalRequiringFcc, int lastApprovalCheckedFCCIndex)> CheckForApprovalRequiringFCCAsync(
        List<FunctionCallContent>? functionCallContents,
        ApprovalRequiredAIFunction[] approvalRequiredFunctions,
        bool hasApprovalRequiringFcc,
        int lastApprovalCheckedFCCIndex)
    {
        // If we already found an approval requiring FCC, we can skip checking the rest.
        if (hasApprovalRequiringFcc)
        {
            return (true, functionCallContents?.Count ?? 0);
        }

        for (; lastApprovalCheckedFCCIndex < (functionCallContents?.Count ?? 0); lastApprovalCheckedFCCIndex++)
        {
            var fcc = functionCallContents![lastApprovalCheckedFCCIndex];
            if (approvalRequiredFunctions.FirstOrDefault(y => y.Name == fcc.Name) is ApprovalRequiredAIFunction approvalFunction &&
                await approvalFunction.RequiresApprovalCallback(new(fcc)))
            {
                hasApprovalRequiringFcc |= true;
            }
        }

        return (hasApprovalRequiringFcc, lastApprovalCheckedFCCIndex);
    }

    /// <summary>
    /// Replaces all <see cref="FunctionCallContent"/> with <see cref="FunctionApprovalRequestContent"/> and ouputs a new list if any of them were replaced.
    /// </summary>
    /// <returns>true if any <see cref="FunctionCallContent"/> was replaced, false otherwise.</returns>
    private static bool TryReplaceFunctionCallsWithApprovalRequests(IList<AIContent> content, out IList<AIContent>? updatedContent)
    {
        updatedContent = null;

        if (content is { Count: > 0 })
        {
            for (int i = 0; i < content.Count; i++)
            {
                if (content[i] is FunctionCallContent fcc)
                {
                    updatedContent ??= [.. content]; // Clone the list if we haven't already
                    var approvalRequest = new FunctionApprovalRequestContent(fcc.CallId, fcc);
                    updatedContent[i] = approvalRequest;
                }
            }
        }

        return updatedContent is not null;
    }

    /// <summary>
    /// Replaces all <see cref="FunctionCallContent"/> from <paramref name="messages"/> with <see cref="FunctionApprovalRequestContent"/>
    /// if any one of them requires approval.
    /// </summary>
    private static async Task<IList<ChatMessage>> ReplaceFunctionCallsWithApprovalRequests(IList<ChatMessage> messages, IList<AITool>? requestOptionsTools, IList<AITool>? additionalTools)
    {
        var outputMessages = messages;
        ApprovalRequiredAIFunction[]? approvalRequiredFunctions = null;

        bool anyApprovalRequired = false;
        List<(int, int)>? allFunctionCallContentIndices = null;

        // Build a list of the indices of all FunctionCallContent items.
        // Also check if any of them require approval.
        for (int i = 0; i < messages.Count; i++)
        {
            var content = messages[i].Contents;
            for (int j = 0; j < content.Count; j++)
            {
                if (content[j] is FunctionCallContent functionCall)
                {
                    allFunctionCallContentIndices ??= [];
                    allFunctionCallContentIndices.Add((i, j));

                    approvalRequiredFunctions ??= (requestOptionsTools ?? []).Concat(additionalTools ?? [])
                        .OfType<ApprovalRequiredAIFunction>()
                        .ToArray();

                    anyApprovalRequired |= approvalRequiredFunctions.FirstOrDefault(x => x.Name == functionCall.Name) is { } approvalFunction && await approvalFunction.RequiresApprovalCallback(new(functionCall));
                }
            }
        }

        // If any function calls were found, and any of them required approval, we should replace all of them with approval requests.
        // This is because we do not have a way to deal with cases where some function calls require approval and others do not, so we just replace all of them.
        if (allFunctionCallContentIndices is not null && anyApprovalRequired)
        {
            // Clone the list so, we don't mutate the input.
            outputMessages = [.. messages];
            int lastMessageIndex = -1;

            foreach (var (messageIndex, contentIndex) in allFunctionCallContentIndices)
            {
                // Clone the message if we didn't already clone it in a previous iteration.
                var message = lastMessageIndex != messageIndex ? outputMessages[messageIndex].Clone() : outputMessages[messageIndex];
                message.Contents = [.. message.Contents];

                var functionCall = (FunctionCallContent)message.Contents[contentIndex];
                message.Contents[contentIndex] = new FunctionApprovalRequestContent(functionCall.CallId, functionCall);
                outputMessages[messageIndex] = message;

                lastMessageIndex = messageIndex;
            }
        }

        return outputMessages;
    }

    /// <summary>
    /// Insert the given <paramref name="preDownstreamCallHistory"/> at the start of the <paramref name="responseMessages"/>.
    /// </summary>
    private static IList<ChatMessage> UpdateResponseMessagesWithPreDownstreamCallHistory(IList<ChatMessage> responseMessages, List<ChatMessage>? preDownstreamCallHistory)
    {
        if (preDownstreamCallHistory?.Count > 0)
        {
            // Since these messages are pre-invocation, we want to insert them at the start of the response messages.
            return [.. preDownstreamCallHistory, .. responseMessages];
        }

        return responseMessages;
    }

    private static ChatResponseUpdate ConvertToolResultMessageToUpdate(ChatMessage message, string? conversationId, string? messageId)
    {
        return new()
        {
            AdditionalProperties = message.AdditionalProperties,
            AuthorName = message.AuthorName,
            ConversationId = conversationId,
            CreatedAt = DateTimeOffset.UtcNow,
            Contents = message.Contents,
            RawRepresentation = message.RawRepresentation,
            ResponseId = messageId,
            MessageId = messageId,
            Role = message.Role,
        };
    }

    private static TimeSpan GetElapsedTime(long startingTimestamp) =>
#if NET
        Stopwatch.GetElapsedTime(startingTimestamp);
#else
        new((long)((Stopwatch.GetTimestamp() - startingTimestamp) * ((double)TimeSpan.TicksPerSecond / Stopwatch.Frequency)));
#endif

    [LoggerMessage(LogLevel.Debug, "Invoking {MethodName}.", SkipEnabledCheck = true)]
    private partial void LogInvoking(string methodName);

    [LoggerMessage(LogLevel.Trace, "Invoking {MethodName}({Arguments}).", SkipEnabledCheck = true)]
    private partial void LogInvokingSensitive(string methodName, string arguments);

    [LoggerMessage(LogLevel.Debug, "{MethodName} invocation completed. Duration: {Duration}", SkipEnabledCheck = true)]
    private partial void LogInvocationCompleted(string methodName, TimeSpan duration);

    [LoggerMessage(LogLevel.Trace, "{MethodName} invocation completed. Duration: {Duration}. Result: {Result}", SkipEnabledCheck = true)]
    private partial void LogInvocationCompletedSensitive(string methodName, TimeSpan duration, string result);

    [LoggerMessage(LogLevel.Debug, "{MethodName} invocation canceled.")]
    private partial void LogInvocationCanceled(string methodName);

    [LoggerMessage(LogLevel.Error, "{MethodName} invocation failed.")]
    private partial void LogInvocationFailed(string methodName, Exception error);

    /// <summary>Provides information about the invocation of a function call.</summary>
    public sealed class FunctionInvocationResult
    {
        /// <summary>
        /// Initializes a new instance of the <see cref="FunctionInvocationResult"/> class.
        /// </summary>
        /// <param name="terminate">Indicates whether the caller should terminate the processing loop.</param>
        /// <param name="status">Indicates the status of the function invocation.</param>
        /// <param name="callContent">Contains information about the function call.</param>
        /// <param name="result">The result of the function call.</param>
        /// <param name="exception">The exception thrown by the function call, if any.</param>
        internal FunctionInvocationResult(bool terminate, FunctionInvocationStatus status, FunctionCallContent callContent, object? result, Exception? exception)
        {
            Terminate = terminate;
            Status = status;
            CallContent = callContent;
            Result = result;
            Exception = exception;
        }

        /// <summary>Gets status about how the function invocation completed.</summary>
        public FunctionInvocationStatus Status { get; }

        /// <summary>Gets the function call content information associated with this invocation.</summary>
        public FunctionCallContent CallContent { get; }

        /// <summary>Gets the result of the function call.</summary>
        public object? Result { get; }

        /// <summary>Gets any exception the function call threw.</summary>
        public Exception? Exception { get; }

        /// <summary>Gets a value indicating whether the caller should terminate the processing loop.</summary>
        public bool Terminate { get; }
    }

    /// <summary>Provides error codes for when errors occur as part of the function calling loop.</summary>
    public enum FunctionInvocationStatus
    {
        /// <summary>The operation completed successfully.</summary>
        RanToCompletion,

        /// <summary>The requested function could not be found.</summary>
        NotFound,

        /// <summary>The function call failed with an exception.</summary>
        Exception,
    }

    private struct ApprovalResultWithRequestMessage
    {
        public FunctionApprovalResponseContent Response { get; set; }
        public ChatMessage? RequestMessage { get; set; }
    }
}
