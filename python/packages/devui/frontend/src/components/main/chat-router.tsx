import { ChatPanel } from './chat-panel';
import { WorkflowChatView } from './workflow-chatview';
import type { AgentInfo, WorkflowInfo, ChatMessage, DebugStreamEvent } from '@/types';

interface ChatRouterProps {
  selectedItem?: AgentInfo;
  workflowInfo?: WorkflowInfo | null;
  workflowLoading?: boolean;
  messages: ChatMessage[];
  debugEvents: DebugStreamEvent[];
  onSendMessage: (message: string) => void;
  isStreaming: boolean;
}

export function ChatRouter({ 
  selectedItem, 
  workflowInfo,
  workflowLoading = false,
  messages, 
  debugEvents, 
  onSendMessage, 
  isStreaming 
}: ChatRouterProps) {
  // Route to workflow chat view for workflows
  if (selectedItem?.type === 'workflow') {
    return (
      <WorkflowChatView 
        workflowInfo={workflowInfo}
        workflowLoading={workflowLoading}
        events={debugEvents} 
        isStreaming={isStreaming}
        onSendMessage={onSendMessage}
      />
    );
  }

  // Default to agent chat panel
  return (
    <ChatPanel
      selectedItem={selectedItem}
      messages={messages}
      onSendMessage={onSendMessage}
      isStreaming={isStreaming}
    />
  );
}