// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Purview.Models.Common;
using Microsoft.Agents.AI.Purview.Models.Jobs;
using Microsoft.Agents.AI.Purview.Models.Requests;
using Microsoft.Agents.AI.Purview.Models.Responses;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Purview;

/// <summary>
/// Processor class that combines protectionScopes, processContent, and contentActivities calls.
/// </summary>
internal sealed class ScopedContentProcessor : IScopedContentProcessor
{
    private readonly IPurviewClient _purviewClient;
    private readonly ICacheProvider _cacheProvider;
    private readonly IChannelHandler _channelHandler;

    /// <summary>
    /// Create a new instance of <see cref="ScopedContentProcessor"/>.
    /// </summary>
    /// <param name="purviewClient">The purview client to use for purview requests.</param>
    /// <param name="cacheProvider">The cache used to store Purview data.</param>
    /// <param name="channelHandler">The channel handler used to manage background jobs.</param>
    public ScopedContentProcessor(IPurviewClient purviewClient, ICacheProvider cacheProvider, IChannelHandler channelHandler)
    {
        this._purviewClient = purviewClient;
        this._cacheProvider = cacheProvider;
        this._channelHandler = channelHandler;
    }

    /// <inheritdoc/>
    public async Task<(bool shouldBlock, string? userId)> ProcessMessagesAsync(IEnumerable<ChatMessage> messages, string? threadId, Activity activity, PurviewSettings purviewSettings, string? userId, CancellationToken cancellationToken)
    {
        List<ProcessContentRequest> pcRequests = await this.MapMessageToPCRequestsAsync(messages, threadId, activity, purviewSettings, userId, cancellationToken).ConfigureAwait(false);

        bool shouldBlock = false;
        string? resolvedUserId = null;

        foreach (ProcessContentRequest pcRequest in pcRequests)
        {
            resolvedUserId = pcRequest.UserId;
            ProcessContentResponse processContentResponse = await this.ProcessContentWithProtectionScopesAsync(pcRequest, cancellationToken).ConfigureAwait(false);
            if (processContentResponse.PolicyActions?.Count > 0)
            {
                foreach (DlpActionInfo policyAction in processContentResponse.PolicyActions)
                {
                    // We need to process all data before blocking, so set the flag and return it outside of this loop.
                    if (policyAction.Action == DlpAction.BlockAccess)
                    {
                        shouldBlock = true;
                    }

                    if (policyAction.RestrictionAction == RestrictionAction.Block)
                    {
                        shouldBlock = true;
                    }
                }
            }
        }

        return (shouldBlock, resolvedUserId);
    }

    private static bool TryGetUserIdFromPayload(IEnumerable<ChatMessage> messages, out string? userId)
    {
        userId = null;

        foreach (ChatMessage message in messages)
        {
            if (message.AdditionalProperties != null &&
                message.AdditionalProperties.TryGetValue(Constants.UserId, out userId) &&
                !string.IsNullOrEmpty(userId))
            {
                return true;
            }
            else if (Guid.TryParse(message.AuthorName, out Guid _))
            {
                userId = message.AuthorName;
                return true;
            }
        }

        return false;
    }

    /// <summary>
    /// Transform a list of ChatMessages into a list of ProcessContentRequests.
    /// </summary>
    /// <param name="messages">The messages to transform.</param>
    /// <param name="threadId">The id of the message thread.</param>
    /// <param name="activity">The activity performed on the content.</param>
    /// <param name="settings">The settings used for purview integration.</param>
    /// <param name="userId">The entra id of the user who made the interaction.</param>
    /// <param name="cancellationToken">The cancellation token used to cancel async operations.</param>
    /// <returns>A list of process content requests.</returns>
    private async Task<List<ProcessContentRequest>> MapMessageToPCRequestsAsync(IEnumerable<ChatMessage> messages, string? threadId, Activity activity, PurviewSettings settings, string? userId, CancellationToken cancellationToken)
    {
        List<ProcessContentRequest> pcRequests = new();
        TokenInfo? tokenInfo = null;

        bool needUserId = userId == null && TryGetUserIdFromPayload(messages, out userId);

        // Only get user info if the tenant id is null or if there's no location.
        // If location is missing, we will create a new location using the client id.
        if (settings.TenantId == null ||
            settings.PurviewAppLocation == null ||
            needUserId)
        {
            tokenInfo = await this._purviewClient.GetUserInfoFromTokenAsync(cancellationToken, settings.TenantId).ConfigureAwait(false);
        }

        string tenantId = settings.TenantId ?? tokenInfo?.TenantId ?? throw new PurviewRequestException("No tenant id provided or inferred for Purview request. Please provide a tenant id in PurviewSettings or configure the TokenCredential to authenticate to a tenant.");

        foreach (ChatMessage message in messages)
        {
            string messageId = message.MessageId ?? Guid.NewGuid().ToString();
            ContentBase content = new PurviewTextContent(message.Text);
            ProcessConversationMetadata conversationmetadata = new(content, messageId, false, $"Agent Framework Message {messageId}")
            {
                CorrelationId = threadId ?? Guid.NewGuid().ToString()
            };
            ActivityMetadata activityMetadata = new(activity);
            PolicyLocation policyLocation;

            if (settings.PurviewAppLocation != null)
            {
                policyLocation = settings.PurviewAppLocation.GetPolicyLocation();
            }
            else if (tokenInfo?.ClientId != null)
            {
                policyLocation = new($"{Constants.ODataGraphNamespace}.policyLocationApplication", tokenInfo.ClientId);
            }
            else
            {
                throw new PurviewRequestException("No app location provided or inferred for Purview request. Please provide an app location in PurviewSettings or configure the TokenCredential to authenticate to an entra app.");
            }

            string appVersion = !string.IsNullOrEmpty(settings.AppVersion) ? settings.AppVersion : "Unknown";

            ProtectedAppMetadata protectedAppMetadata = new(policyLocation)
            {
                Name = settings.AppName,
                Version = appVersion
            };
            IntegratedAppMetadata integratedAppMetadata = new()
            {
                Name = settings.AppName,
                Version = appVersion
            };

            DeviceMetadata deviceMetadata = new()
            {
                OperatingSystemSpecifications = new()
                {
                    OperatingSystemPlatform = "Unknown",
                    OperatingSystemVersion = "Unknown"
                }
            };
            ContentToProcess contentToProcess = new(new List<ProcessContentMetadataBase> { conversationmetadata }, activityMetadata, deviceMetadata, integratedAppMetadata, protectedAppMetadata);

            if (userId == null &&
                tokenInfo?.UserId != null)
            {
                userId = tokenInfo.UserId;
            }

            if (string.IsNullOrEmpty(userId))
            {
                throw new PurviewRequestException("No user id provided or inferred for Purview request. Please provide an Entra user id in each message's AuthorName, set a default Entra user id in PurviewSettings, or configure the TokenCredential to authenticate to an Entra user.");
            }

            ProcessContentRequest pcRequest = new(contentToProcess, userId, tenantId);
            pcRequests.Add(pcRequest);
        }

        return pcRequests;
    }

    /// <summary>
    /// Orchestrates process content and protection scopes calls.
    /// </summary>
    /// <param name="pcRequest">The process content request.</param>
    /// <param name="cancellationToken">The cancellation token used to cancel async operations.</param>
    /// <returns>A process content response. This could be a response from the process content API or a response generated from a content activities call.</returns>
    private async Task<ProcessContentResponse> ProcessContentWithProtectionScopesAsync(ProcessContentRequest pcRequest, CancellationToken cancellationToken)
    {
        ProtectionScopesRequest psRequest = CreateProtectionScopesRequest(pcRequest, pcRequest.UserId, pcRequest.TenantId, pcRequest.CorrelationId);

        ProtectionScopesCacheKey cacheKey = new(psRequest);

        ProtectionScopesResponse? cacheResponse = await this._cacheProvider.GetAsync<ProtectionScopesCacheKey, ProtectionScopesResponse>(cacheKey, cancellationToken).ConfigureAwait(false);

        ProtectionScopesResponse psResponse;

        if (cacheResponse != null)
        {
            psResponse = cacheResponse;
        }
        else
        {
            psResponse = await this._purviewClient.GetProtectionScopesAsync(psRequest, cancellationToken).ConfigureAwait(false);
            await this._cacheProvider.SetAsync(cacheKey, psResponse, cancellationToken).ConfigureAwait(false);
        }

        pcRequest.ScopeIdentifier = psResponse.ScopeIdentifier;

        (bool shouldProcess, List<DlpActionInfo> dlpActions, ExecutionMode executionMode) = CheckApplicableScopes(pcRequest, psResponse);

        if (shouldProcess)
        {
            if (executionMode == ExecutionMode.EvaluateOffline)
            {
                this._channelHandler.QueueJob(new ProcessContentJob(pcRequest));
                return new ProcessContentResponse();
            }

            ProcessContentResponse pcResponse = await this._purviewClient.ProcessContentAsync(pcRequest, cancellationToken).ConfigureAwait(false);

            if (pcResponse.ProtectionScopeState == ProtectionScopeState.Modified)
            {
                await this._cacheProvider.RemoveAsync(cacheKey, cancellationToken).ConfigureAwait(false);
            }

            pcResponse = CombinePolicyActions(pcResponse, dlpActions);
            return pcResponse;
        }

        ContentActivitiesRequest caRequest = new(pcRequest.UserId, pcRequest.TenantId, pcRequest.ContentToProcess, pcRequest.CorrelationId);
        this._channelHandler.QueueJob(new ContentActivityJob(caRequest));

        return new ProcessContentResponse();
    }

    /// <summary>
    /// Dedupe policy actions received from the service.
    /// </summary>
    /// <param name="pcResponse">The process content response which may contain DLP actions.</param>
    /// <param name="actionInfos">DLP actions returned from protection scopes.</param>
    /// <returns>The process content response with the protection scopes DLP actions added. Actions are deduplicated.</returns>
    private static ProcessContentResponse CombinePolicyActions(ProcessContentResponse pcResponse, List<DlpActionInfo>? actionInfos)
    {
        if (actionInfos == null || actionInfos.Count == 0)
        {
            return pcResponse;
        }

        if (pcResponse.PolicyActions == null)
        {
            pcResponse.PolicyActions = actionInfos;
            return pcResponse;
        }

        List<DlpActionInfo> pcActionInfos = new(pcResponse.PolicyActions);
        pcActionInfos.AddRange(actionInfos);
        pcResponse.PolicyActions = pcActionInfos;
        return pcResponse;
    }

    /// <summary>
    /// Check if any scopes are applicable to the request.
    /// </summary>
    /// <param name="pcRequest">The process content request.</param>
    /// <param name="psResponse">The protection scopes response that was returned for the process content request.</param>
    /// <returns>A bool indicating if the content needs to be processed. A list of applicable actions from the scopes response, and the execution mode for the process content request.</returns>
    private static (bool shouldProcess, List<DlpActionInfo> dlpActions, ExecutionMode executionMode) CheckApplicableScopes(ProcessContentRequest pcRequest, ProtectionScopesResponse psResponse)
    {
        ProtectionScopeActivities requestActivity = TranslateActivity(pcRequest.ContentToProcess.ActivityMetadata.Activity);

        // The location data type is formatted as microsoft.graph.{locationType}
        // Sometimes a '#' gets appended by graph during responses, so for the sake of simplicity,
        // Split it by '.' and take the last segment. We'll do a case-insensitive endsWith later.
        string[] locationSegments = pcRequest.ContentToProcess.ProtectedAppMetadata.ApplicationLocation.DataType.Split('.');
        string locationType = locationSegments.Length > 0 ? locationSegments[locationSegments.Length - 1] : pcRequest.ContentToProcess.ProtectedAppMetadata.ApplicationLocation.Value;

        string locationValue = pcRequest.ContentToProcess.ProtectedAppMetadata.ApplicationLocation.Value;
        List<DlpActionInfo> dlpActions = new();
        bool shouldProcess = false;
        ExecutionMode executionMode = ExecutionMode.EvaluateOffline;

        foreach (var scope in psResponse.Scopes ?? Array.Empty<PolicyScopeBase>())
        {
            bool activityMatch = scope.Activities.HasFlag(requestActivity);
            bool locationMatch = false;

            foreach (var location in scope.Locations ?? Array.Empty<PolicyLocation>())
            {
                locationMatch = location.DataType.EndsWith(locationType, StringComparison.OrdinalIgnoreCase) && location.Value.Equals(locationValue, StringComparison.OrdinalIgnoreCase);
            }

            if (activityMatch && locationMatch)
            {
                shouldProcess = true;

                if (scope.ExecutionMode == ExecutionMode.EvaluateInline)
                {
                    executionMode = ExecutionMode.EvaluateInline;
                }

                if (scope.PolicyActions != null)
                {
                    dlpActions.AddRange(scope.PolicyActions);
                }
            }
        }

        return (shouldProcess, dlpActions, executionMode);
    }

    /// <summary>
    /// Create a ProtectionScopesRequest for the given content ProcessContentRequest.
    /// </summary>
    /// <param name="pcRequest">The process content request.</param>
    /// <param name="userId">The entra user id of the user who sent the data.</param>
    /// <param name="tenantId">The tenant id of the user who sent the data.</param>
    /// <param name="correlationId">The correlation id of the request.</param>
    /// <returns>The protection scopes request generated from the process content request.</returns>
    private static ProtectionScopesRequest CreateProtectionScopesRequest(ProcessContentRequest pcRequest, string userId, string tenantId, Guid correlationId)
    {
        return new ProtectionScopesRequest(userId, tenantId)
        {
            Activities = TranslateActivity(pcRequest.ContentToProcess.ActivityMetadata.Activity),
            Locations = new List<PolicyLocation> { pcRequest.ContentToProcess.ProtectedAppMetadata.ApplicationLocation },
            DeviceMetadata = pcRequest.ContentToProcess.DeviceMetadata,
            IntegratedAppMetadata = pcRequest.ContentToProcess.IntegratedAppMetadata,
            CorrelationId = correlationId
        };
    }

    /// <summary>
    /// Map process content activity to protection scope activity.
    /// </summary>
    /// <param name="activity">The process content activity.</param>
    /// <returns>The protection scopes activity.</returns>
    private static ProtectionScopeActivities TranslateActivity(Activity activity)
    {
        switch (activity)
        {
            case Activity.Unknown:
                return ProtectionScopeActivities.None;
            case Activity.UploadText:
                return ProtectionScopeActivities.UploadText;
            case Activity.UploadFile:
                return ProtectionScopeActivities.UploadFile;
            case Activity.DownloadText:
                return ProtectionScopeActivities.DownloadText;
            case Activity.DownloadFile:
                return ProtectionScopeActivities.DownloadFile;
            default:
                return ProtectionScopeActivities.UnknownFutureValue;
        }
    }
}
