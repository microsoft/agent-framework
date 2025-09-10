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
import { Card, CardContent, CardTitle } from "@/components/ui/card";
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
              value={typeof value === "string" && value ? value : (typeof defaultValue === "string" ? defaultValue : enumValues[0])}
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
  const [showAdvanced, setShowAdvanced] = useState(false);

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
  };

  const updateField = (name: string, value: unknown) => {
    setFormData((prev) => ({
      ...prev,
      [name]: value,
    }));
  };

  // Determine form layout
  const properties = inputSchema.properties || {};
  const fieldNames = Object.keys(properties);
  const isSimpleInput = inputSchema.type === "string" || 
    (inputSchema.type === "object" && fieldNames.length === 1);
  
  const primaryField = inputSchema.type === "string" 
    ? { name: "value", schema: inputSchema, placeholder: inputSchema.description || "Enter workflow input..." }
    : inputSchema.type === "object" && fieldNames.length === 1
    ? { name: fieldNames[0], schema: properties[fieldNames[0]], placeholder: properties[fieldNames[0]].description || `Enter ${fieldNames[0]}...` }
    : null;

  return (
    <div className={cn("h-full flex flex-col", className)}>
      <Card className="h-full flex flex-col">
        <div className="border-b border-border px-4 py-3 bg-muted flex-shrink-0">
          <div className="flex items-center justify-between mb-2">
            <CardTitle className="text-sm">Run Workflow</CardTitle>
            {!isSimpleInput && fieldNames.length > 1 && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setShowAdvanced(!showAdvanced)}
                className="text-xs"
              >
                {showAdvanced ? (
                  <>Hide Fields <ChevronUp className="h-3 w-3 ml-1" /></>
                ) : (
                  <>Show All <ChevronDown className="h-3 w-3 ml-1" /></>
                )}
              </Button>
            )}
          </div>
          
          <div className="text-xs text-muted-foreground mb-3">
            <strong>Type:</strong>{" "}
            <code className="bg-muted-foreground/20 px-1 py-0.5 rounded">
              {inputTypeName}
            </code>
            {inputSchema.type === "object" && (
              <span className="ml-2">
                ({fieldNames.length} field{fieldNames.length !== 1 ? 's' : ''})
              </span>
            )}
          </div>

          {/* Run Button - Always visible at top */}
          <Button
            type="submit"
            form="workflow-form"
            disabled={
              isSubmitting ||
              (isSimpleInput && primaryField && (
                typeof formData[primaryField.name] !== "string" ||
                !(formData[primaryField.name] as string).trim()
              ))
            }
            className="w-full"
            size="default"
          >
            <Send className="h-4 w-4 mr-2" />
            {isSubmitting ? "Running..." : "Run Workflow"}
          </Button>
        </div>

        <CardContent className="flex-1 p-4 overflow-hidden">
          <form id="workflow-form" onSubmit={handleSubmit} className="h-full">
            <div className="h-full overflow-y-auto space-y-3">
              {/* Simple input */}
              {isSimpleInput && primaryField && (
                <div className="space-y-2">
                  <Label htmlFor={primaryField.name} className="text-sm font-medium">
                    {primaryField.name === "value" ? "Input" : primaryField.name}
                  </Label>
                  <Input
                    id={primaryField.name}
                    value={
                      typeof formData[primaryField.name] === "string"
                        ? (formData[primaryField.name] as string)
                        : ""
                    }
                    onChange={(e) => updateField(primaryField.name, e.target.value)}
                    placeholder={primaryField.placeholder}
                    disabled={isSubmitting}
                  />
                  {primaryField.schema.description && (
                    <p className="text-xs text-muted-foreground">
                      {primaryField.schema.description}
                    </p>
                  )}
                </div>
              )}

              {/* Complex form fields */}
              {!isSimpleInput && (
                <div className="space-y-3">
                  {fieldNames.slice(0, showAdvanced ? fieldNames.length : 2).map((fieldName) => (
                    <FormField
                      key={fieldName}
                      name={fieldName}
                      schema={properties[fieldName] as JSONSchemaProperty}
                      value={formData[fieldName]}
                      onChange={(value) => updateField(fieldName, value)}
                    />
                  ))}
                  
                  {!showAdvanced && fieldNames.length > 2 && (
                    <div className="text-center">
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() => setShowAdvanced(true)}
                        className="text-xs text-muted-foreground"
                      >
                        +{fieldNames.length - 2} more fields
                      </Button>
                    </div>
                  )}
                </div>
              )}
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
