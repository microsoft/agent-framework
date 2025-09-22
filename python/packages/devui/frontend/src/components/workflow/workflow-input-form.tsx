import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
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

interface FormFieldProps {
  name: string;
  schema: JSONSchemaProperty;
  value: unknown;
  onChange: (value: unknown) => void;
}

function FormField({ name, schema, value, onChange }: FormFieldProps) {
  const { type, description, enum: enumValues, default: defaultValue } = schema;

  // Determine if this field should span full width
  const shouldSpanFullWidth =
    schema.format === "textarea" ||
    (description && description.length > 100) ||
    type === "object" ||
    type === "array";

  const shouldSpanTwoColumns =
    type === "object" ||
    schema.format === "textarea" ||
    (description && description.length > 50);

  const fieldContent = (() => {
    // Handle different field types based on JSON Schema
    switch (type) {
      case "string":
        if (enumValues) {
          // Enum select
          return (
            <div className="space-y-2">
              <Label htmlFor={name}>{name}</Label>
              <Select
                value={
                  typeof value === "string" && value
                    ? value
                    : typeof defaultValue === "string"
                    ? defaultValue
                    : enumValues[0]
                }
                onValueChange={(val) => onChange(val)}
              >
                <SelectTrigger>
                  <SelectValue placeholder={`Select ${name}`} />
                </SelectTrigger>
                <SelectContent>
                  {enumValues.map((option: string) => (
                    <SelectItem key={option} value={option}>
                      {option}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {description && (
                <p className="text-sm text-muted-foreground">{description}</p>
              )}
            </div>
          );
        } else if (
          schema.format === "textarea" ||
          (description && description.length > 100)
        ) {
          // Multi-line text
          return (
            <div className="space-y-2">
              <Label htmlFor={name}>{name}</Label>
              <Textarea
                id={name}
                value={typeof value === "string" ? value : ""}
                onChange={(e) => onChange(e.target.value)}
                placeholder={
                  typeof defaultValue === "string"
                    ? defaultValue
                    : `Enter ${name}`
                }
                rows={2}
              />
              {description && (
                <p className="text-sm text-muted-foreground">{description}</p>
              )}
            </div>
          );
        } else {
          // Single-line text
          return (
            <div className="space-y-2">
              <Label htmlFor={name}>{name}</Label>
              <Input
                id={name}
                type="text"
                value={typeof value === "string" ? value : ""}
                onChange={(e) => onChange(e.target.value)}
                placeholder={
                  typeof defaultValue === "string"
                    ? defaultValue
                    : `Enter ${name}`
                }
              />
              {description && (
                <p className="text-sm text-muted-foreground">{description}</p>
              )}
            </div>
          );
        }

      case "number":
        return (
          <div className="space-y-2">
            <Label htmlFor={name}>{name}</Label>
            <Input
              id={name}
              type="number"
              value={typeof value === "number" ? value : ""}
              onChange={(e) => {
                const val = parseFloat(e.target.value);
                onChange(isNaN(val) ? "" : val);
              }}
              placeholder={
                typeof defaultValue === "number"
                  ? defaultValue.toString()
                  : `Enter ${name}`
              }
            />
            {description && (
              <p className="text-sm text-muted-foreground">{description}</p>
            )}
          </div>
        );

      case "boolean":
        return (
          <div className="space-y-2">
            <div className="flex items-center space-x-2">
              <Checkbox
                id={name}
                checked={Boolean(value)}
                onCheckedChange={(checked) => onChange(checked)}
              />
              <Label htmlFor={name}>{name}</Label>
            </div>
            {description && (
              <p className="text-sm text-muted-foreground">{description}</p>
            )}
          </div>
        );

      case "array":
        return (
          <div className="space-y-2">
            <Label htmlFor={name}>{name}</Label>
            <Textarea
              id={name}
              value={
                Array.isArray(value)
                  ? value.join(", ")
                  : typeof value === "string"
                  ? value
                  : ""
              }
              onChange={(e) => {
                const arrayValue = e.target.value
                  .split(",")
                  .map((item) => item.trim())
                  .filter((item) => item.length > 0);
                onChange(arrayValue);
              }}
              placeholder="Enter items separated by commas"
              rows={2}
            />
            {description && (
              <p className="text-sm text-muted-foreground">{description}</p>
            )}
          </div>
        );

      case "object":
      default:
        // For complex objects or unknown types, use JSON textarea
        return (
          <div className="space-y-2">
            <Label htmlFor={name}>{name}</Label>
            <Textarea
              id={name}
              value={
                typeof value === "object" && value !== null
                  ? JSON.stringify(value, null, 2)
                  : typeof value === "string"
                  ? value
                  : ""
              }
              onChange={(e) => {
                try {
                  const parsed = JSON.parse(e.target.value);
                  onChange(parsed);
                } catch {
                  // Keep raw string value if not valid JSON
                  onChange(e.target.value);
                }
              }}
              placeholder='{"key": "value"}'
              rows={3}
            />
            {description && (
              <p className="text-sm text-muted-foreground">{description}</p>
            )}
          </div>
        );
    }
  })();

  // Return the field with appropriate grid column spanning
  const getColumnSpan = () => {
    if (shouldSpanFullWidth) return "md:col-span-3 xl:col-span-4";
    if (shouldSpanTwoColumns) return "xl:col-span-2";
    return "";
  };

  return <div className={getColumnSpan()}>{fieldContent}</div>;
}

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
  const isEmbedded = className?.includes('embedded');
  const [formData, setFormData] = useState<Record<string, unknown>>({});
  const [loading, setLoading] = useState(false);

  // Determine field info
  const properties = inputSchema.properties || {};
  const fieldNames = Object.keys(properties);
  const isSimpleInput = inputSchema.type === "string" && !inputSchema.enum;
  const primaryField = isSimpleInput ? "value" : fieldNames[0];
  const canSubmit = primaryField
    ? formData[primaryField] !== undefined && formData[primaryField] !== ""
    : Object.keys(formData).length > 0;

  // Initialize form data
  useEffect(() => {
    if (inputSchema.type === "string") {
      setFormData({ value: inputSchema.default || "" });
    } else if (inputSchema.type === "object" && inputSchema.properties) {
      const initialData: Record<string, unknown> = {};
      Object.entries(inputSchema.properties).forEach(([key, fieldSchema]) => {
        if (fieldSchema.default !== undefined) {
          initialData[key] = fieldSchema.default;
        } else if (fieldSchema.enum && fieldSchema.enum.length > 0) {
          initialData[key] = fieldSchema.enum[0];
        }
      });
      setFormData(initialData);
    }
  }, [inputSchema]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);

    // Simplified submission logic
    if (inputSchema.type === "string") {
      onSubmit({ input: formData.value || "" });
    } else if (inputSchema.type === "object") {
      const properties = inputSchema.properties || {};
      const fieldNames = Object.keys(properties);

      if (fieldNames.length === 1) {
        const fieldName = fieldNames[0];
        onSubmit({ [fieldName]: formData[fieldName] || "" });
      } else {
        onSubmit(formData);
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

  const updateField = (fieldName: string, value: unknown) => {
    setFormData((prev) => ({
      ...prev,
      [fieldName]: value,
    }));
  };

  // If embedded, just show the form directly
  if (isEmbedded) {
    return (
      <form onSubmit={handleSubmit} className={className}>
        <div className="grid grid-cols-1 gap-4">
          {/* Simple input */}
          {isSimpleInput && primaryField && (
            <FormField
              name="Input"
              schema={inputSchema}
              value={formData.value}
              onChange={(value) => updateField("value", value)}
            />
          )}

          {/* Complex form fields */}
          {!isSimpleInput && (
            <>
              {fieldNames.map((fieldName) => (
                <FormField
                  key={fieldName}
                  name={fieldName}
                  schema={properties[fieldName] as JSONSchemaProperty}
                  value={formData[fieldName]}
                  onChange={(value) => updateField(fieldName, value)}
                />
              ))}
            </>
          )}
        </div>

        <div className="flex gap-2 mt-4 justify-end">
          <Button
            type="submit"
            disabled={loading || !canSubmit}
            size="default"
          >
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
              <div className="grid grid-cols-1 md:grid-cols-3 xl:grid-cols-4 gap-8 max-w-none">
                {/* Simple input */}
                {isSimpleInput && primaryField && (
                  <div className="md:col-span-3 xl:col-span-4">
                    <FormField
                      name="Input"
                      schema={inputSchema}
                      value={formData.value}
                      onChange={(value) => updateField("value", value)}
                    />
                    {inputSchema.description && (
                      <p className="text-sm text-muted-foreground mt-2">
                        {inputSchema.description}
                      </p>
                    )}
                  </div>
                )}

                {/* Complex form fields - Show all */}
                {!isSimpleInput && (
                  <>
                    {fieldNames.map((fieldName) => (
                      <FormField
                        key={fieldName}
                        name={fieldName}
                        schema={properties[fieldName] as JSONSchemaProperty}
                        value={formData[fieldName]}
                        onChange={(value) => updateField(fieldName, value)}
                      />
                    ))}
                  </>
                )}
              </div>
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
