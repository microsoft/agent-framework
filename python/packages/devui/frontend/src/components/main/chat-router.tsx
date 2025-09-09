import { ChatPanel } from "./chat-panel";
import { WorkflowChatView } from "./workflow-chatview";
import type {
  AgentInfo,
  WorkflowInfo,
  ChatMessage,
  DebugStreamEvent,
  RunAgentRequest,
} from "@/types";

interface ChatRouterProps {
  selectedItem?: AgentInfo | WorkflowInfo | null;
  workflowInfo?: WorkflowInfo | null;
  workflowLoading?: boolean;
  messages: ChatMessage[];
  debugEvents: DebugStreamEvent[];
  onSendMessage: (request: RunAgentRequest["messages"]) => void;
  onSendWorkflowData?: (inputData: Record<string, unknown>) => void;
  isStreaming: boolean;
}

export function ChatRouter({
  selectedItem,
  workflowInfo,
  workflowLoading = false,
  messages,
  debugEvents,
  onSendMessage,
  onSendWorkflowData,
  isStreaming,
}: ChatRouterProps) {
  // Route to workflow chat view for workflows
  if (selectedItem?.type === "workflow") {
    return (
      <WorkflowChatView
        workflowInfo={workflowInfo}
        workflowLoading={workflowLoading}
        events={debugEvents}
        isStreaming={isStreaming}
        onSendMessage={onSendMessage}
        onSendWorkflowData={onSendWorkflowData}
      />
    );
  } else if (selectedItem?.type === "agent") {
    // Default to agent chat panel
    return (
      <ChatPanel
        selectedItem={selectedItem}
        messages={messages}
        onSendMessage={onSendMessage}
        isStreaming={isStreaming}
      />
    );
  } else {
    return (
      <div className="flex-1 flex items-center justify-center text-muted-foreground">
        Select an agent or workflow to get started.
      </div>
    );
  }
}
