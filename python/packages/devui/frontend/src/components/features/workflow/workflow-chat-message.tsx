import {
  Message,
  MessageAvatar,
  MessageContent,
} from "@/components/ai-elements/message";
import {
  Reasoning,
  ReasoningTrigger,
  ReasoningContent,
} from "@/components/ai-elements/reasoning";
import { Response } from "@/components/ai-elements/response";
import {
  Tool,
  ToolHeader,
  ToolContent,
  ToolInput,
  ToolOutput,
} from "@/components/ai-elements/tool";
import { Actions, Action } from "@/components/ai-elements/actions";
import { generateExecutorAvatar } from "@/utils/avatar-utils";
import { Copy, User } from "lucide-react";

export interface ChatToolCall {
  id: string;
  name: string;
  input: unknown;
  output?: unknown;
  error?: string;
  state: "input-streaming" | "input-available" | "output-available" | "output-error";
}

export interface ChatMessage {
  id: string;
  executorId: string;
  executorName?: string;
  role: "user" | "assistant";
  content: string;
  isIntermediate: boolean;
  toolCalls?: ChatToolCall[];
  timestamp: string;
  state: "pending" | "streaming" | "completed" | "error";
}

interface WorkflowChatMessageProps {
  message: ChatMessage;
}

export function WorkflowChatMessage({ message }: WorkflowChatMessageProps) {
  const handleCopy = () => {
    navigator.clipboard.writeText(message.content).catch((err) => {
      console.error("Failed to copy to clipboard:", err);
    });
  };

  // User message - avatar on right
  if (message.role === "user") {
    return (
      <Message from="user">
        <MessageAvatar src="" name="User">
          <div className="flex items-center justify-center w-full h-full bg-primary text-primary-foreground rounded-full">
            <User className="w-4 h-4" />
          </div>
        </MessageAvatar>
        <MessageContent variant="contained">
          <div className="whitespace-pre-wrap break-words">{message.content}</div>
        </MessageContent>
      </Message>
    );
  }

  // Assistant message (executor)
  const { initials, color } = generateExecutorAvatar(message.executorId);

  return (
    <Message from="assistant">
      <MessageAvatar src="" name={initials}>
        <div
          className="flex items-center justify-center w-full h-full text-white font-semibold text-xs rounded-full"
          style={{ backgroundColor: color }}
        >
          {initials}
        </div>
      </MessageAvatar>
      <MessageContent variant="contained">
        <div className="flex flex-col gap-2.5 w-full">
          {/* Executor name - subtle header */}
          {message.executorName && (
            <div className="text-[10px] font-medium text-muted-foreground/70 uppercase tracking-wider -mb-1">
              {message.executorName}
            </div>
          )}

          {/* Tool calls */}
          {message.toolCalls && message.toolCalls.length > 0 && (
            <div className="flex flex-col gap-2">
              {message.toolCalls.map((toolCall) => (
                <Tool
                  key={toolCall.id}
                  defaultOpen={false}
                >
                  <ToolHeader
                    title={toolCall.name}
                    type="tool-call"
                    state={toolCall.state}
                  />
                  <ToolContent>
                    <ToolInput input={toolCall.input} />
                    {toolCall.output !== undefined && (
                      <ToolOutput
                        output={toolCall.output as never}
                        errorText={toolCall.error}
                      />
                    )}
                  </ToolContent>
                </Tool>
              ))}
            </div>
          )}

          {/* Message content */}
          {message.content && (
            <>
              {message.isIntermediate ? (
                <Reasoning
                  isStreaming={message.state === "streaming"}
                  defaultOpen={false}
                >
                  <ReasoningTrigger />
                  <ReasoningContent>{message.content}</ReasoningContent>
                </Reasoning>
              ) : (
                <Response>{message.content}</Response>
              )}
            </>
          )}

          {/* Copy action */}
          {message.content && (
            <Actions>
              <Action tooltip="Copy message" onClick={handleCopy}>
                <Copy className="w-3.5 h-3.5" />
              </Action>
            </Actions>
          )}
        </div>
      </MessageContent>
    </Message>
  );
}
