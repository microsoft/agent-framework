import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogClose,
  DialogFooter,
} from "@/components/ui/dialog";
import { Send } from "lucide-react";
import { cn } from "@/lib/utils";
import type { JSONSchemaProperty } from "@/types";
import {
  SchemaFormRenderer,
  filterEmptyOptionalFields,
  detectChatMessagePattern,
} from "./schema-form-renderer";

interface WorkflowInputFormProps {
  inputSchema: JSONSchemaProperty;
  inputTypeName: string;
  onSubmit: (formData: unknown) => void;
  isSubmitting?: boolean;
  className?: string;
}

export function WorkflowInputForm({
  inputSchema,
  inputTypeName,
  onSubmit,
  isSubmitting = false,
  className,
}: WorkflowInputFormProps) {
  const [isModalOpen, setIsModalOpen] = useState(false);

  // Check if we're in embedded mode (being used inside another modal)
  const isEmbedded = className?.includes("embedded");
  const [formData, setFormData] = useState<Record<string, unknown>>({});
  const [loading, setLoading] = useState(false);

  // Determine field info
  const properties = inputSchema.properties || {};
  const fieldNames = Object.keys(properties);
  const requiredFields = inputSchema.required || [];
  const isSimpleInput = inputSchema.type === "string" && !inputSchema.enum;
  const isNullInput = inputSchema.type === "null";
  const isPrimitiveInput = inputSchema.type === "integer" || inputSchema.type === "number";
  const isBooleanInput = inputSchema.type === "boolean";
  const isArrayInput = inputSchema.type === "array";

  // Detect Message-like pattern for auto-filling role
  const isChatMessageLike = detectChatMessagePattern(inputSchema, requiredFields);

  // Validation: check if required fields are filled
  const canSubmit = isNullInput
    ? true
    : isBooleanInput
    ? true
    : isPrimitiveInput
    ? formData.value !== undefined && formData.value !== ""
    : isArrayInput
    ? true
    : isSimpleInput
    ? formData.value !== undefined && formData.value !== ""
    : requiredFields.length > 0
      ? requiredFields.every((fieldName) => {
          // Auto-filled fields are always valid
          if (
            isChatMessageLike &&
            fieldName === "role" &&
            formData["role"] === "user"
          ) {
            return true;
          }
          return formData[fieldName] !== undefined && formData[fieldName] !== "";
        })
      : Object.keys(formData).length > 0;

  // Initialize form data with defaults
  useEffect(() => {
    if (inputSchema.type === "null") {
      setFormData({});
    } else if (inputSchema.type === "string") {
      setFormData({ value: inputSchema.default || "" });
    } else if (inputSchema.type === "integer" || inputSchema.type === "number") {
      setFormData({ value: inputSchema.default ?? "" });
    } else if (inputSchema.type === "boolean") {
      setFormData({ value: inputSchema.default ?? false });
    } else if (inputSchema.type === "array") {
      setFormData({ value: inputSchema.default ?? [] });
    } else if (inputSchema.type === "object" && inputSchema.properties) {
      const initialData: Record<string, unknown> = {};
      Object.entries(inputSchema.properties).forEach(([key, fieldSchema]) => {
        if (fieldSchema.default !== undefined) {
          initialData[key] = fieldSchema.default;
        } else if (fieldSchema.enum && fieldSchema.enum.length > 0) {
          initialData[key] = fieldSchema.enum[0];
        }
      });

      // Auto-fill role="user" for Message-like inputs
      if (isChatMessageLike && !initialData["role"]) {
        initialData["role"] = "user";
      }

      setFormData(initialData);
    }
  }, [inputSchema, isChatMessageLike]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);

    // Simplified submission logic
    if (inputSchema.type === "null") {
      onSubmit({});
    } else if (inputSchema.type === "string") {
      onSubmit({ input: formData.value || "" });
    } else if (inputSchema.type === "integer") {
      const intStr = String(formData.value).trim();
      const intValue = intStr === "" ? 0 : parseInt(intStr, 10);
      onSubmit({ input: intValue });
    } else if (inputSchema.type === "number") {
      const numStr = String(formData.value).trim();
      const numValue = numStr === "" ? 0 : parseFloat(numStr);
      onSubmit({ input: numValue });
    } else if (inputSchema.type === "boolean") {
      onSubmit({ input: Boolean(formData.value) });
    } else if (inputSchema.type === "array") {
      onSubmit({ input: Array.isArray(formData.value) ? formData.value : [] });
    } else if (inputSchema.type === "object") {
      const properties = inputSchema.properties || {};
      const fieldNames = Object.keys(properties);

      if (fieldNames.length === 1) {
        const fieldName = fieldNames[0];
        onSubmit({ [fieldName]: formData[fieldName] || "" });
      } else {
        // Filter out empty optional fields before submission
        const filteredData = filterEmptyOptionalFields(inputSchema, formData);
        onSubmit(filteredData);
      }
    } else {
      onSubmit(formData);
    }

    // Only close modal if not embedded
    if (!isEmbedded) {
      setIsModalOpen(false);
    }
    setLoading(false);
  };

  const handleFormChange = (newValues: Record<string, unknown>) => {
    setFormData(newValues);
  };

  // Simple string input renderer (for non-object schemas)
  const renderSimpleInput = () => (
    <div className="space-y-2">
      <Label htmlFor="simple-input">Input</Label>
      <Textarea
        id="simple-input"
        value={typeof formData.value === "string" ? formData.value : ""}
        onChange={(e) => setFormData({ value: e.target.value })}
        placeholder={
          typeof inputSchema.default === "string"
            ? inputSchema.default
            : "Enter input"
        }
        rows={4}
        className="min-w-[300px] w-full"
      />
      {inputSchema.description && (
        <p className="text-sm text-muted-foreground">{inputSchema.description}</p>
      )}
    </div>
  );

  // Integer/Number input renderer
  const renderNumberInput = () => (
    <div className="space-y-2">
      <Label htmlFor="number-input">
        {inputSchema.type === "integer" ? "Integer" : "Number"} Input
      </Label>
      <Input
        id="number-input"
        type="number"
        step={inputSchema.type === "integer" ? "1" : "any"}
        value={typeof formData.value === "number" ? formData.value : ""}
        onChange={(e) => {
          const rawValue = e.target.value;
          if (rawValue === "") {
            setFormData({ value: undefined });
            return;
          }
          const val =
            inputSchema.type === "integer"
              ? parseInt(rawValue, 10)
              : parseFloat(rawValue);
          setFormData({ value: isNaN(val) ? undefined : val });
        }}
        placeholder={
          typeof inputSchema.default === "number"
            ? inputSchema.default.toString()
            : `Enter ${inputSchema.type === "integer" ? "integer" : "number"}`
        }
      />
      {inputSchema.description && (
        <p className="text-sm text-muted-foreground">{inputSchema.description}</p>
      )}
    </div>
  );

  // Boolean input renderer
  const renderBooleanInput = () => (
    <div className="space-y-2">
      <div className="flex items-center space-x-2">
        <Checkbox
          id="boolean-input"
          checked={Boolean(formData.value)}
          onCheckedChange={(checked) => setFormData({ value: checked })}
        />
        <Label htmlFor="boolean-input">
          Value: {formData.value ? "true" : "false"}
        </Label>
      </div>
      {inputSchema.description && (
        <p className="text-sm text-muted-foreground">{inputSchema.description}</p>
      )}
    </div>
  );

  // Array input renderer
  const renderArrayInput = () => (
    <div className="space-y-2">
      <Label htmlFor="array-input">
        Array{inputSchema.items?.type ? ` of ${inputSchema.items.type}s` : ""}
      </Label>
      <Textarea
        id="array-input"
        value={
          Array.isArray(formData.value)
            ? (formData.value as unknown[]).join(", ")
            : typeof formData.value === "string"
              ? formData.value
              : ""
        }
        onChange={(e) => {
          const rawItems = e.target.value
            .split(",")
            .map((item) => item.trim())
            .filter((item) => item.length > 0);

          const typedItems = rawItems.map((item) => {
            const itemType = inputSchema.items?.type;
            switch (itemType) {
              case "integer": {
                const parsed = parseInt(item, 10);
                return Number.isNaN(parsed) ? item : parsed;
              }
              case "number": {
                const parsed = parseFloat(item);
                return Number.isNaN(parsed) ? item : parsed;
              }
              case "boolean": {
                const lower = item.toLowerCase();
                if (lower === "true") return true;
                if (lower === "false") return false;
                return item;
              }
              default:
                return item;
            }
          });

          setFormData({ value: typedItems });
        }}
        placeholder="Enter items separated by commas"
        rows={3}
      />
      {inputSchema.description && (
        <p className="text-sm text-muted-foreground">{inputSchema.description}</p>
      )}
    </div>
  );

  // Determine which renderer to use for non-object schemas
  const renderPrimitiveInput = () => {
    if (isNullInput) return null;
    if (isSimpleInput) return renderSimpleInput();
    if (isPrimitiveInput) return renderNumberInput();
    if (isBooleanInput) return renderBooleanInput();
    if (isArrayInput) return renderArrayInput();
    return null;
  };

  // Check if input type is a non-object type (primitive, array, etc.)
  const isNonObjectSchema = isNullInput || isSimpleInput || isPrimitiveInput || isBooleanInput || isArrayInput;

  // If embedded, just show the form directly
  if (isEmbedded) {
    return (
      <form onSubmit={handleSubmit} className={className}>
        {/* Primitive/simple input types */}
        {isNonObjectSchema && renderPrimitiveInput()}

        {/* Complex form fields using SchemaFormRenderer */}
        {!isNonObjectSchema && (
          <SchemaFormRenderer
            schema={inputSchema}
            values={formData}
            onChange={handleFormChange}
            disabled={loading}
            hideFields={isChatMessageLike ? ["role"] : []}
            layout="grid"
          />
        )}

        <div className="flex gap-2 mt-4 justify-end">
          <Button type="submit" disabled={loading || !canSubmit} size="default">
            <Send className="h-4 w-4" />
            {loading ? "Running..." : "Run Workflow"}
          </Button>
        </div>
      </form>
    );
  }

  return (
    <>
      {/* Sidebar Form Component */}
      <div className={cn("flex flex-col", className)}>
        {/* Header with Run Button */}
        <div className="border-b border-border px-4 py-3 bg-muted">
          <CardTitle className="text-sm mb-3">Run Workflow</CardTitle>

          {/* Run Button - Opens Modal */}
          <Button
            onClick={() => setIsModalOpen(true)}
            disabled={isSubmitting}
            className="w-full"
            size="default"
          >
            <Send className="h-4 w-4 mr-2" />
            {isSubmitting ? "Running..." : "Run Workflow"}
          </Button>
        </div>

        {/* Info Section */}
        <div className="px-4 py-3">
          <div className="text-sm text-muted-foreground">
            <strong>Input Type:</strong>{" "}
            <code className="bg-muted px-1 py-0.5 rounded">
              {inputTypeName}
            </code>
            {inputSchema.type === "object" && inputSchema.properties && (
              <span className="ml-2">
                ({Object.keys(inputSchema.properties).length} field
                {Object.keys(inputSchema.properties).length !== 1 ? "s" : ""})
              </span>
            )}
          </div>
          <p className="text-xs text-muted-foreground mt-2">
            Click "Run Workflow" to configure inputs and execute
          </p>
        </div>
      </div>

      {/* Modal with the actual form */}
      <Dialog open={isModalOpen} onOpenChange={setIsModalOpen}>
        <DialogContent className="w-full max-w-md sm:max-w-lg md:max-w-2xl lg:max-w-4xl xl:max-w-5xl max-h-[90vh] flex flex-col">
          <DialogHeader>
            <DialogTitle>Run Workflow</DialogTitle>
            <DialogClose onClose={() => setIsModalOpen(false)} />
          </DialogHeader>

          {/* Form Info */}
          <div className="px-8 py-4 border-b flex-shrink-0">
            <div className="text-sm text-muted-foreground">
              <div className="flex items-center gap-3">
                <span className="font-medium">Input Type:</span>
                <code className="bg-muted px-3 py-1 text-xs font-mono">
                  {inputTypeName}
                </code>
                {inputSchema.type === "object" && (
                  <span className="text-xs text-muted-foreground">
                    {fieldNames.length} field
                    {fieldNames.length !== 1 ? "s" : ""}
                  </span>
                )}
              </div>
            </div>
          </div>

          {/* Scrollable Form Content */}
          <div className="px-8 py-6 overflow-y-auto flex-1 min-h-0">
            <form id="workflow-modal-form" onSubmit={handleSubmit}>
              {/* Primitive/simple input types */}
              {isNonObjectSchema && renderPrimitiveInput()}

              {/* Complex form fields using SchemaFormRenderer */}
              {!isNonObjectSchema && (
                <SchemaFormRenderer
                  schema={inputSchema}
                  values={formData}
                  onChange={handleFormChange}
                  disabled={loading}
                  hideFields={isChatMessageLike ? ["role"] : []}
                  layout="grid"
                />
              )}
            </form>
          </div>

          {/* Footer */}
          <div className="px-8 py-4 border-t flex-shrink-0">
            <DialogFooter>
              <Button
                variant="outline"
                onClick={() => setIsModalOpen(false)}
                disabled={loading}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                form="workflow-modal-form"
                disabled={loading || !canSubmit}
              >
                <Send className="h-4 w-4 mr-2" />
                {loading ? "Running..." : "Run Workflow"}
              </Button>
            </DialogFooter>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
