import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Send, ChevronDown, ChevronUp } from "lucide-react";
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

  // Handle different field types based on JSON Schema
  switch (type) {
    case "string":
      if (enumValues) {
        // Enum select
        return (
          <div className="space-y-2">
            <Label htmlFor={name}>{name}</Label>
            <Select
              value={typeof value === "string" && value ? value : (defaultValue || enumValues[0])}
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
              rows={3}
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

    case "integer":
    case "number":
      return (
        <div className="space-y-2">
          <Label htmlFor={name}>{name}</Label>
          <Input
            id={name}
            type="number"
            step={type === "integer" ? "1" : "any"}
            value={typeof value === "number" ? value.toString() : ""}
            onChange={(e) => {
              const val = e.target.value;
              onChange(
                val === ""
                  ? null
                  : type === "integer"
                  ? parseInt(val, 10)
                  : parseFloat(val)
              );
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
              checked={typeof value === "boolean" ? value : false}
              onCheckedChange={(checked) => onChange(!!checked)}
            />
            <Label htmlFor={name}>{name}</Label>
          </div>
          {description && (
            <p className="text-sm text-muted-foreground">{description}</p>
          )}
        </div>
      );

    case "array":
      // Simple array input - user enters comma-separated values
      return (
        <div className="space-y-2">
          <Label htmlFor={name}>{name}</Label>
          <Input
            id={name}
            type="text"
            value={Array.isArray(value) ? value.join(", ") : ""}
            onChange={(e) => {
              const val = e.target.value;
              onChange(val ? val.split(",").map((s) => s.trim()) : []);
            }}
            placeholder="Enter comma-separated values"
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
            rows={4}
          />
          {description && (
            <p className="text-sm text-muted-foreground">{description}</p>
          )}
        </div>
      );
  }
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
  const [formData, setFormData] = useState<Record<string, unknown>>({});
  const [isExpanded, setIsExpanded] = useState(false);

  // Initialize form with default values
  useEffect(() => {
    if (inputSchema?.properties) {
      const initialData: Record<string, unknown> = {};
      Object.entries(inputSchema.properties).forEach(([key, fieldSchema]) => {
        if (fieldSchema.default !== undefined) {
          initialData[key] = fieldSchema.default;
        } else if (fieldSchema.enum && fieldSchema.enum.length > 0) {
          // Set first enum value as default for literal types
          initialData[key] = fieldSchema.enum[0];
        }
      });
      setFormData(initialData);
    }
  }, [inputSchema]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    // For simple string input types, wrap in object structure for backend API
    if (inputSchema.type === "string") {
      onSubmit({ input: formData.value || "" });
    } else if (
      inputSchema.type === "object" &&
      Object.keys(inputSchema.properties || {}).length === 1
    ) {
      // For single-field objects (enhanced from basic types), wrap the field value
      const fieldName = Object.keys(inputSchema.properties || {})[0];
      onSubmit({ [fieldName]: formData[fieldName] || "" });
    } else {
      // For complex objects, pass the entire form data
      onSubmit(formData);
    }
  };

  const updateField = (name: string, value: unknown) => {
    setFormData((prev) => ({
      ...prev,
      [name]: value,
    }));
  };

  // Handle simple string input (most common case)
  if (inputSchema.type === "string") {
    return (
      <Card className={cn("border-t border-border", className)}>
        <CardHeader className="pb-4">
          <div className="flex items-center justify-between">
            <CardTitle className="text-lg">Run Workflow</CardTitle>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setIsExpanded(!isExpanded)}
              className="p-2"
            >
              {isExpanded ? (
                <ChevronUp className="h-4 w-4" />
              ) : (
                <ChevronDown className="h-4 w-4" />
              )}
            </Button>
          </div>
        </CardHeader>
        <CardContent className={cn("space-y-4", !isExpanded && "pb-4")}>
          {isExpanded && (
            <div className="text-sm text-muted-foreground">
              Input Type:{" "}
              <code className="bg-muted px-1 py-0.5 rounded">
                {inputTypeName}
              </code>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="flex gap-2">
              <Input
                value={typeof formData.value === "string" ? formData.value : ""}
                onChange={(e) => updateField("value", e.target.value)}
                placeholder={
                  inputSchema.description || "Enter workflow input..."
                }
                disabled={isSubmitting}
                className="flex-1"
              />
              <Button
                type="submit"
                disabled={
                  isSubmitting ||
                  typeof formData.value !== "string" ||
                  !formData.value.trim()
                }
                size="default"
              >
                <Send className="h-4 w-4 mr-2" />
                Run
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    );
  }

  // Check if it's an object schema with a single field (enhanced from basic type)
  const properties = inputSchema.properties || {};
  const fieldNames = Object.keys(properties);

  // If it's an object with a single field, treat it as a simple input with field name
  if (inputSchema.type === "object" && fieldNames.length === 1) {
    const fieldName = fieldNames[0];
    const fieldSchema = properties[fieldName];
    const placeholder = fieldSchema.description || `Enter ${fieldName}...`;

    return (
      <Card className={cn("border-t border-border", className)}>
        <CardHeader className="pb-4">
          <div className="flex items-center justify-between">
            <CardTitle className="text-lg">Run Workflow</CardTitle>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setIsExpanded(!isExpanded)}
              className="p-2"
            >
              {isExpanded ? (
                <ChevronUp className="h-4 w-4" />
              ) : (
                <ChevronDown className="h-4 w-4" />
              )}
            </Button>
          </div>
        </CardHeader>
        <CardContent className={cn("space-y-4", !isExpanded && "pb-4")}>
          {isExpanded && (
            <div className="text-sm text-muted-foreground">
              Input Type:{" "}
              <code className="bg-muted px-1 py-0.5 rounded">
                {inputTypeName}
              </code>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="flex gap-2">
              <Input
                value={
                  typeof formData[fieldName] === "string"
                    ? formData[fieldName]
                    : ""
                }
                onChange={(e) => updateField(fieldName, e.target.value)}
                placeholder={placeholder}
                disabled={isSubmitting}
                className="flex-1"
              />
              <Button
                type="submit"
                disabled={
                  isSubmitting ||
                  typeof formData[fieldName] !== "string" ||
                  !formData[fieldName].trim()
                }
                size="default"
              >
                <Send className="h-4 w-4 mr-2" />
                Run
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    );
  }

  // Handle complex object inputs
  const complexProperties = inputSchema.properties || {};

  return (
    <Card className={cn("border-t border-border", className)}>
      <CardHeader className="pb-4">
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg">Run Workflow</CardTitle>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setIsExpanded(!isExpanded)}
            className="p-2"
          >
            {isExpanded ? (
              <ChevronUp className="h-4 w-4" />
            ) : (
              <ChevronDown className="h-4 w-4" />
            )}
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="text-sm text-muted-foreground">
          Input Type:{" "}
          <code className="bg-muted px-1 py-0.5 rounded">{inputTypeName}</code>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className={cn("space-y-4", !isExpanded && "hidden")}>
            {Object.entries(complexProperties).map(
              ([fieldName, fieldSchema]) => (
                <FormField
                  key={fieldName}
                  name={fieldName}
                  schema={fieldSchema as JSONSchemaProperty}
                  value={formData[fieldName]}
                  onChange={(value) => updateField(fieldName, value)}
                />
              )
            )}
          </div>

          <div className="flex justify-end pt-4 border-t">
            <Button type="submit" disabled={isSubmitting} size="default">
              <Send className="h-4 w-4 mr-2" />
              {isSubmitting ? "Running..." : "Run Workflow"}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
