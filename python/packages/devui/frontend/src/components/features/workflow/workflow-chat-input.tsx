import {
  PromptInput,
  PromptInputBody,
  PromptInputTextarea,
  PromptInputFooter,
  PromptInputTools,
  PromptInputSubmit,
} from "@/components/ai-elements/prompt-input";
import type { JSONSchemaProperty } from "@/types";
import type { FormEvent } from "react";

interface WorkflowChatInputProps {
  inputSchema: JSONSchemaProperty;
  onSubmit: (data: Record<string, unknown>) => void;
  disabled?: boolean;
}

export function WorkflowChatInput({
  inputSchema,
  onSubmit,
  disabled = false,
}: WorkflowChatInputProps) {
  const handleSubmit = (
    message: { text?: string },
    _event: FormEvent<HTMLFormElement>
  ) => {
    const text = message.text || "";

    // Convert text input to appropriate format based on input schema
    let payload: Record<string, unknown>;

    if (inputSchema.type === "string") {
      // Simple string input
      payload = { input: text };
    } else if (inputSchema.type === "object" && inputSchema.properties) {
      const properties = inputSchema.properties;
      const fieldNames = Object.keys(properties);

      if (fieldNames.length === 1) {
        // Single field object - use the field name
        const fieldName = fieldNames[0];
        payload = { [fieldName]: text };
      } else {
        // Multiple fields - check for ChatMessage-like pattern
        const isChatMessageLike =
          properties.role?.type === "string" &&
          fieldNames.some((f) => ["text", "message", "content"].includes(f));

        if (isChatMessageLike) {
          // ChatMessage pattern: auto-fill role=user and use text field
          const textField =
            fieldNames.find((f) => ["text", "message", "content"].includes(f)) ||
            "text";
          payload = {
            role: "user",
            [textField]: text,
          };
        } else {
          // Default: try to parse as JSON, fallback to object with 'input' key
          try {
            const parsed = JSON.parse(text);
            payload = typeof parsed === "object" ? parsed : { input: text };
          } catch {
            payload = { input: text };
          }
        }
      }
    } else {
      // Unknown schema type - pass as is
      payload = { input: text };
    }

    onSubmit(payload);
  };

  return (
    <PromptInput
      onSubmit={handleSubmit}
      className="border-t border-border p-4"
    >
      <PromptInputBody>
        <PromptInputTextarea
          placeholder="Type your workflow input..."
          disabled={disabled}
          className="resize-none"
        />
      </PromptInputBody>
      <PromptInputFooter>
        <PromptInputTools>{/* Empty - no additional tools */}</PromptInputTools>
        <PromptInputSubmit disabled={disabled} />
      </PromptInputFooter>
    </PromptInput>
  );
}
