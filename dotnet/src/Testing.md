# AG-UI Testing Plan

This document outlines the unit testing strategy for the AG-UI implementation, focusing on types and members with logic beyond simple constructors or property accessors.

## Client Library (Microsoft.Agents.AI.AGUI)

### AGUIAgent (AGUIAgent.cs)
* **RunAsync**
  * RunAsync_AggregatesStreamingUpdates_ReturnsCompleteMessages
  * RunAsync_WithEmptyUpdateStream_ReturnsEmptyResponse
  * RunAsync_WithNullMessages_ThrowsArgumentNullException
  * RunAsync_WithNullThread_CreatesNewThread
  * RunAsync_WithNonAGUIAgentThread_ThrowsInvalidOperationException

* **RunStreamingAsync**
  * RunStreamingAsync_YieldsAllEvents_FromServerStream
  * RunStreamingAsync_WithNullMessages_ThrowsArgumentNullException
  * RunStreamingAsync_WithNullThread_CreatesNewThread
  * RunStreamingAsync_WithNonAGUIAgentThread_ThrowsInvalidOperationException
  * RunStreamingAsync_GeneratesUniqueRunId_ForEachInvocation
  * RunStreamingAsync_NotifiesThreadOfNewMessages_AfterCompletion

* **DeserializeThread**
  * DeserializeThread_WithValidState_DeserializesSuccessfully
  * DeserializeThread_PreservesThreadId_FromSerializedState
  * DeserializeThread_WithMissingThreadId_ThrowsInvalidOperationException

### AGUIAgentThread (AGUIAgentThread.cs)
* **Constructor (from JsonElement)**
  * Constructor_WithValidThreadId_DeserializesSuccessfully
  * Constructor_WithMissingThreadId_ThrowsInvalidOperationException
  * Constructor_WithMissingWrappedState_ThrowsInvalidOperationException
  * Constructor_UnwrapsAndRestores_BaseState

* **Serialize**
  * Serialize_IncludesThreadId_InSerializedState
  * Serialize_WrapsBaseState_Correctly
  * Serialize_RoundTrip_PreservesThreadIdAndMessages

### AGUIHttpService (AGUIHttpService.cs)
* **PostRunAsync**
  * PostRunAsync_SendsRequestAndParsesSSEStream_Successfully
  * PostRunAsync_WithNonSuccessStatusCode_ThrowsHttpRequestException
  * PostRunAsync_DeserializesMultipleEventTypes_Correctly
  * PostRunAsync_WithEmptyEventStream_CompletesSuccessfully
  * PostRunAsync_WithCancellationToken_CancelsRequest

## Shared Types

### AgentRunResponseUpdateAGUIExtensions (Shared/AgentRunResponseUpdateAGUIExtensions.cs)
* **AsChatResponseUpdatesAsync** (client-only)
  * AsChatResponseUpdatesAsync_ConvertsRunStartedEvent_ToRunStartedContent
  * AsChatResponseUpdatesAsync_ConvertsRunFinishedEvent_ToRunFinishedContent
  * AsChatResponseUpdatesAsync_ConvertsRunErrorEvent_ToRunErrorContent
  * AsChatResponseUpdatesAsync_ConvertsTextMessageSequence_ToTextUpdatesWithCorrectRole
  * AsChatResponseUpdatesAsync_WithTextMessageStartWhileMessageInProgress_ThrowsInvalidOperationException
  * AsChatResponseUpdatesAsync_WithTextMessageEndForWrongMessageId_ThrowsInvalidOperationException
  * AsChatResponseUpdatesAsync_MaintainsMessageContext_AcrossMultipleContentEvents

* **AsAGUIEventStreamAsync** (server-only)
  * AsAGUIEventStreamAsync_YieldsRunStartedEvent_AtBeginningWithCorrectIds
  * AsAGUIEventStreamAsync_YieldsRunFinishedEvent_AtEndWithCorrectIds
  * AsAGUIEventStreamAsync_ConvertsTextContentUpdates_ToTextMessageEvents
  * AsAGUIEventStreamAsync_GroupsConsecutiveUpdates_WithSameMessageId
  * AsAGUIEventStreamAsync_WithRoleChanges_EmitsProperTextMessageStartEvents
  * AsAGUIEventStreamAsync_EmitsTextMessageEndEvent_WhenMessageIdChanges

### AGUIChatMessageExtensions (Shared/AGUIChatMessageExtensions.cs)
* **AsChatMessages**
  * AsChatMessages_WithEmptyCollection_ReturnsEmptyList
  * AsChatMessages_WithSingleMessage_ConvertsToChatMessageCorrectly
  * AsChatMessages_WithMultipleMessages_PreservesOrder
  * AsChatMessages_MapsAllSupportedRoleTypes_Correctly

* **AsAGUIMessages**
  * AsAGUIMessages_WithEmptyCollection_ReturnsEmptyList
  * AsAGUIMessages_WithSingleMessage_ConvertsToAGUIMessageCorrectly
  * AsAGUIMessages_WithMultipleMessages_PreservesOrder
  * AsAGUIMessages_PreservesMessageId_WhenPresent

* **MapChatRole**
  * MapChatRole_WithSystemRole_ReturnsChatRoleSystem
  * MapChatRole_WithUserRole_ReturnsChatRoleUser
  * MapChatRole_WithAssistantRole_ReturnsChatRoleAssistant
  * MapChatRole_WithDeveloperRole_ReturnsDeveloperChatRole
  * MapChatRole_WithUnknownRole_ThrowsInvalidOperationException

## Server Library (Microsoft.Agents.AI.Hosting.AGUI.AspNetCore)

### AGUIEndpointRouteBuilderExtensions (AGUIEndpointRouteBuilderExtensions.cs)
* **MapAGUIAgent**
  * MapAGUIAgent_MapsEndpoint_AtSpecifiedPattern
  * MapAGUIAgent_WithNullOrInvalidInput_Returns400BadRequest
  * MapAGUIAgent_InvokesAgentFactory_WithCorrectMessagesAndContext
  * MapAGUIAgent_ReturnsSSEResponseStream_WithCorrectContentType
  * MapAGUIAgent_PassesCancellationToken_ToAgentExecution
  * MapAGUIAgent_ConvertsInputMessages_ToChatMessagesBeforeFactory

### AGUIServerSentEventsResult (AGUIServerSentEventsResult.cs)
* **ExecuteAsync**
  * ExecuteAsync_SetsCorrectResponseHeaders_ContentTypeAndCacheControl
  * ExecuteAsync_SerializesEventsInSSEFormat_WithDataPrefixAndNewlines
  * ExecuteAsync_FlushesResponse_AfterEachEvent
  * ExecuteAsync_WithEmptyEventStream_CompletesSuccessfully
  * ExecuteAsync_RespectsCancellationToken_WhenCancelled
  * ExecuteAsync_WithNullHttpContext_ThrowsArgumentNullException

## JSON Serialization Tests

### AGUIJsonSerializerContext (Shared/AGUIJsonSerializerContext.cs)
These tests validate proper serialization/deserialization across all AG-UI protocol types:

* **RunAgentInput**
  * RunAgentInput_Serializes_WithAllRequiredFields
  * RunAgentInput_Deserializes_FromJsonWithRequiredFields
  * RunAgentInput_HandlesOptionalFields_StateContextAndForwardedProperties
  * RunAgentInput_ValidatesMinimumMessageCount_MinLengthOne
  * RunAgentInput_RoundTrip_PreservesAllData

* **RunStartedEvent**
  * RunStartedEvent_Serializes_WithCorrectEventType
  * RunStartedEvent_Includes_ThreadIdAndRunIdInOutput
  * RunStartedEvent_Deserializes_FromJsonCorrectly
  * RunStartedEvent_RoundTrip_PreservesData

* **RunFinishedEvent**
  * RunFinishedEvent_Serializes_WithCorrectEventType
  * RunFinishedEvent_Includes_ThreadIdRunIdAndOptionalResult
  * RunFinishedEvent_Deserializes_FromJsonCorrectly
  * RunFinishedEvent_RoundTrip_PreservesData

* **RunErrorEvent**
  * RunErrorEvent_Serializes_WithCorrectEventType
  * RunErrorEvent_Includes_MessageAndOptionalCode
  * RunErrorEvent_Deserializes_FromJsonCorrectly
  * RunErrorEvent_RoundTrip_PreservesData

* **TextMessageStartEvent**
  * TextMessageStartEvent_Serializes_WithCorrectEventType
  * TextMessageStartEvent_Includes_MessageIdAndRole
  * TextMessageStartEvent_Deserializes_FromJsonCorrectly
  * TextMessageStartEvent_RoundTrip_PreservesData

* **TextMessageContentEvent**
  * TextMessageContentEvent_Serializes_WithCorrectEventType
  * TextMessageContentEvent_Includes_MessageIdAndDelta
  * TextMessageContentEvent_Deserializes_FromJsonCorrectly
  * TextMessageContentEvent_RoundTrip_PreservesData

* **TextMessageEndEvent**
  * TextMessageEndEvent_Serializes_WithCorrectEventType
  * TextMessageEndEvent_Includes_MessageId
  * TextMessageEndEvent_Deserializes_FromJsonCorrectly
  * TextMessageEndEvent_RoundTrip_PreservesData

* **AGUIMessage**
  * AGUIMessage_Serializes_WithIdRoleAndContent
  * AGUIMessage_Deserializes_FromJsonCorrectly
  * AGUIMessage_RoundTrip_PreservesData
  * AGUIMessage_Validates_RequiredFields

* **BaseEvent polymorphic deserialization**
  * BaseEvent_Deserializes_RunStartedEventAsBaseEvent
  * BaseEvent_Deserializes_RunFinishedEventAsBaseEvent
  * BaseEvent_Deserializes_RunErrorEventAsBaseEvent
  * BaseEvent_Deserializes_TextMessageStartEventAsBaseEvent
  * BaseEvent_Deserializes_TextMessageContentEventAsBaseEvent
  * BaseEvent_Deserializes_TextMessageEndEventAsBaseEvent
  * BaseEvent_DistinguishesEventTypes_BasedOnTypeField

* **AGUIAgentThreadState** (client-only)
  * AGUIAgentThreadState_Serializes_WithThreadIdAndWrappedState
  * AGUIAgentThreadState_Deserializes_FromJsonCorrectly
  * AGUIAgentThreadState_RoundTrip_PreservesThreadIdAndNestedState

## Content Types (Public API)

### RunStartedContent (RunStartedContent.cs)
No tests needed - simple data class with no logic.

### RunFinishedContent (RunFinishedContent.cs)
No tests needed - simple data class with no logic.

### RunErrorContent (RunErrorContent.cs)
No tests needed - simple data class with no logic.

## Notes

- All tests follow the Arrange/Act/Assert pattern
- Tests use the `this.` prefix for accessing class members
- Private classes used only for testing are marked as `sealed`
- Async test methods use the `Async` suffix
- Tests focus on behavior validation, not implementation details
- Tests avoid redundant validation of features handled by the compiler or framework
- Moq library is used for mocking dependencies where needed
- Tests are grouped by type/class in separate test files
