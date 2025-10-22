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
    <div className="border-t border-border bg-gradient-to-b from-muted/5 to-background">
      <PromptInput
        onSubmit={handleSubmit}
        className="p-4"
      >
        <PromptInputBody className="bg-background/50 backdrop-blur-sm border border-border/50 rounded-xl">
          <PromptInputTextarea
            placeholder="Input to your workflow..."
            disabled={disabled}
            className="resize-none bg-transparent placeholder:text-muted-foreground/60"
          />
        </PromptInputBody>
        <PromptInputFooter className="mt-2">
          <PromptInputTools />
          <PromptInputSubmit
            disabled={disabled}
            className="bg-primary hover:bg-primary/90 text-primary-foreground"
          />
        </PromptInputFooter>
      </PromptInput>
    </div>
  );
}
