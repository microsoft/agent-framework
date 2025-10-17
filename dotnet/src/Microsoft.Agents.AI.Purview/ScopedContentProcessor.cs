// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Purview.Models.Common;
using Microsoft.Agents.AI.Purview.Models.Requests;
using Microsoft.Agents.AI.Purview.Models.Responses;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Purview;

/// <summary>
/// Processor class that combines protectionScopes, processContent, and contentActivities calls.
/// </summary>
internal sealed class ScopedContentProcessor
{
    private readonly PurviewClient _purviewClient;

    /// <summary>
    /// Create a new instance of <see cref="ScopedContentProcessor"/>.
    /// </summary>
    /// <param name="purviewClient">The purview client to use for purview requests.</param>
    public ScopedContentProcessor(PurviewClient purviewClient)
    {
        this._purviewClient = purviewClient;
    }

    /// <summary>
    /// Process a list of messages.
    /// The list of messages should be a prompt or response.
    /// </summary>
    /// <param name="messages">A list of <see cref="ChatMessage"/> objects sent to the agent or received from the agent..</param>
    /// <param name="threadId">The thread where the messages were sent.</param>
    /// <param name="activity">An activity to indicate prompt or response.</param>
    /// <param name="purviewSettings">Purview settings containing tenant id, app name, etc.</param>
    /// <param name="userId">The user who sent the prompt or is receiving the response.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns></returns>
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
    /// <param name="messages"></param>
    /// <param name="threadId"></param>
    /// <param name="activity"></param>
    /// <param name="settings"></param>
    /// <param name="userId"></param>
    /// <param name="cancellationToken"></param>
    /// <returns></returns>
    public async Task<List<ProcessContentRequest>> MapMessageToPCRequestsAsync(IEnumerable<ChatMessage> messages, string? threadId, Activity activity, PurviewSettings settings, string? userId, CancellationToken cancellationToken)
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
            if (settings.TenantId != null)
            {
                tokenInfo = await this._purviewClient.GetUserInfoFromTokenAsync(cancellationToken, settings.TenantId).ConfigureAwait(false);
            }
            else
            {
                tokenInfo = await this._purviewClient.GetUserInfoFromTokenAsync(cancellationToken).ConfigureAwait(false);
            }
        }

        string tenantId = settings.TenantId ?? tokenInfo?.TenantId ?? throw new InvalidOperationException("No tenant id provided or inferred for Purview request. Please provide a tenant id in PurviewSettings or configure the TokenCredential to authenticate to a tenant.");

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
                throw new InvalidOperationException("No app location provided or inferred for Purview request. Please provide an app location in PurviewSettings or configure the TokenCredential to authenticate to an entra app.");
            }

            ProtectedAppMetadata protectedAppMetadata = new(policyLocation)
            {
                Name = settings.AppName,
                Version = "1.0",
            };
            IntegratedAppMetadata integratedAppMetadata = new()
            {
                Name = settings.AppName,
                Version = "1.0"
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
                throw new InvalidOperationException("No user id provided or inferred for Purview request. Please provide an Entra user id in each message's AuthorName, set a default Entra user id in PurviewSettings, or configure the TokenCredential to authenticate to an Entra user.");
            }

            ProcessContentRequest pcRequest = new(contentToProcess, userId, tenantId);
            pcRequests.Add(pcRequest);
        }

        return pcRequests;
    }

    /// <summary>
    /// Orchestrates process content and protection scopes calls.
    /// </summary>
    /// <param name="pcRequest"></param>
    /// <param name="cancellationToken"></param>
    /// <returns></returns>
    private async Task<ProcessContentResponse> ProcessContentWithProtectionScopesAsync(ProcessContentRequest pcRequest, CancellationToken cancellationToken)
    {
        ProtectionScopesRequest psRequest = CreateProtectionScopesRequest(pcRequest, pcRequest.UserId, pcRequest.TenantId, pcRequest.CorrelationId);
        ProtectionScopesResponse psResponse = await this._purviewClient.GetProtectionScopesAsync(psRequest, cancellationToken).ConfigureAwait(false);

        (bool shouldProcess, List<DlpActionInfo> dlpActions) = CheckApplicableScopes(pcRequest, psResponse);

        if (shouldProcess)
        {
            ProcessContentResponse pcResponse = await this._purviewClient.ProcessContentAsync(pcRequest, cancellationToken).ConfigureAwait(false);
            pcResponse = CombinePolicyActions(pcResponse, dlpActions);
            return pcResponse;
        }

        ContentActivitiesRequest caRequest = new(pcRequest.UserId, pcRequest.TenantId, pcRequest.ContentToProcess, pcRequest.CorrelationId);
        ContentActivitiesResponse caResponse = await this._purviewClient.SendContentActivitiesAsync(caRequest, cancellationToken).ConfigureAwait(false);

        ProcessContentResponse mappedPCResponse = new();

        if (caResponse.Error != null)
        {
            ProcessingError error = new()
            {
                Details = new List<ClassificationErrorBase>()
                {
                    new()
                    {
                        ErrorCode = caResponse.Error?.Code ?? "Unknown ErrorCode",
                        Message = caResponse.Error?.Message ?? "Unknown Error Message"
                    }
                }
            };

            mappedPCResponse.ProcessingErrors = new List<ProcessingError>
            {
                error
            };
        }

        return mappedPCResponse;
    }

    /// <summary>
    /// Dedupe policy actions received from the service.
    /// </summary>
    /// <param name="pcResponse"></param>
    /// <param name="actionInfos"></param>
    /// <returns></returns>
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

        HashSet<DlpAction> dlpActions = new();

        foreach (DlpActionInfo action in actionInfos)
        {
            dlpActions.Add(action.Action);
        }

        foreach (DlpActionInfo action in pcResponse.PolicyActions)
        {
            dlpActions.Add(action.Action);
        }

        if (dlpActions.Count == 0)
        {
            return pcResponse;
        }

        List<DlpActionInfo> dedupedActions = new();

        foreach (DlpAction action in dlpActions)
        {
            dedupedActions.Add(new DlpActionInfo { Action = action });
        }

        pcResponse.PolicyActions = dedupedActions;
        return pcResponse;
    }

    /// <summary>
    /// Check if any scopes are applicable to the request.
    /// </summary>
    /// <param name="pcRequest"></param>
    /// <param name="psResponse"></param>
    /// <returns></returns>
    private static (bool shouldProcess, List<DlpActionInfo> dlpActions) CheckApplicableScopes(ProcessContentRequest pcRequest, ProtectionScopesResponse psResponse)
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

                if (scope.PolicyActions != null)
                {
                    dlpActions.AddRange(scope.PolicyActions);
                }
            }
        }

        return (shouldProcess, dlpActions);
    }

    /// <summary>
    /// Create a ProtectionScopesRequest for the given content ProcessContentRequest.
    /// </summary>
    /// <param name="pcRequest"></param>
    /// <param name="userId"></param>
    /// <param name="tenantId"></param>
    /// <param name="correlationId"></param>
    /// <returns></returns>
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
    /// <param name="activity"></param>
    /// <returns></returns>
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
