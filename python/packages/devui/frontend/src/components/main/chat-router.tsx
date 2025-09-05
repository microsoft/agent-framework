import { ChatPanel } from './chat-panel';
import { WorkflowChatView } from './workflow-chatview';
import type { AgentInfo, WorkflowInfo, ChatMessage, DebugStreamEvent } from '@/types';

interface ChatRouterProps {
  selectedItem?: AgentInfo;
  workflowInfo?: WorkflowInfo | null;
  messages: ChatMessage[];
  debugEvents: DebugStreamEvent[];
  onSendMessage: (message: string) => void;
  isStreaming: boolean;
}

export function ChatRouter({ 
  selectedItem, 
  workflowInfo,
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