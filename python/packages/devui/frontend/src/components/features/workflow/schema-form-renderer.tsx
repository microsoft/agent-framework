import { useState } from "react";
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
import { ChevronDown, ChevronUp } from "lucide-react";
import type { JSONSchemaProperty } from "@/types";

// ============================================================================
// Field Type Detection (from WorkflowInputForm)
// ============================================================================

function isShortField(fieldName: string): boolean {
  const shortFieldNames = [
    "name",
    "title",
    "id",
    "key",
    "label",
    "type",
    "status",
    "tag",
    "category",
    "code",
    "username",
    "password",
    "email",
  ];
  return shortFieldNames.includes(fieldName.toLowerCase());
}

function shouldFieldBeTextarea(
  fieldName: string,
  schema: JSONSchemaProperty
): boolean {
  return (
    schema.format === "textarea" ||
    (!!schema.description && schema.description.length > 100) ||
    (schema.type === "string" && !schema.enum && !isShortField(fieldName))
  );
}

function getFieldColumnSpan(
  fieldName: string,
  schema: JSONSchemaProperty
): string {
  const isTextarea = shouldFieldBeTextarea(fieldName, schema);
  const hasLongDescription =
    !!schema.description && schema.description.length > 150;

  if (isTextarea || hasLongDescription) {
    return "md:col-span-2 lg:col-span-3 xl:col-span-4";
  }

  if (
    schema.type === "array" ||
    (!!schema.description && schema.description.length > 80)
  ) {
    return "xl:col-span-2";
  }

  return "";
}

// ============================================================================
// ChatMessage Pattern Detection (from WorkflowInputForm)
// ============================================================================

function detectChatMessagePattern(
  schema: JSONSchemaProperty,
  requiredFields: string[]
): boolean {
  if (schema.type !== "object" || !schema.properties) return false;

  const properties = schema.properties;
  const optionalFields = Object.keys(properties).filter(
    (name) => !requiredFields.includes(name)
  );

  return (
    requiredFields.includes("role") &&
    optionalFields.some((f) => ["text", "message", "content"].includes(f)) &&
    properties["role"]?.type === "string"
  );
}

// ============================================================================
// Form Field Component (from WorkflowInputForm)
// ============================================================================

interface FormFieldProps {
  name: string;
  schema: JSONSchemaProperty;
  value: unknown;
  onChange: (value: unknown) => void;
  isRequired?: boolean;
  isReadOnly?: boolean; // NEW: for HIL display-only fields
}

function FormField({
  name,
  schema,
  value,
  onChange,
  isRequired = false,
  isReadOnly = false,
}: FormFieldProps) {
  const { type, description, enum: enumValues, default: defaultValue } = schema;
  const isTextarea = shouldFieldBeTextarea(name, schema);

  const renderInput = () => {
    // Read-only display (for HIL request context)
    if (isReadOnly) {
      return (
        <div className="space-y-2">
          <Label htmlFor={name} className="text-muted-foreground">
            {name}
          </Label>
          <div className="text-sm p-2 bg-muted rounded border">
            {typeof value === "object"
              ? JSON.stringify(value, null, 2)
              : String(value)}
          </div>
          {description && (
            <p className="text-xs text-muted-foreground">{description}</p>
          )}
        </div>
      );
    }

    switch (type) {
      case "string":
        if (enumValues) {
          // Enum select
          return (
            <div className="space-y-2">
              <Label htmlFor={name}>
                {name}
                {isRequired && <span className="text-destructive ml-1">*</span>}
              </Label>
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
        } else if (isTextarea) {
          // Multi-line text
          return (
            <div className="space-y-2">
              <Label htmlFor={name}>
                {name}
                {isRequired && <span className="text-destructive ml-1">*</span>}
              </Label>
              <Textarea
                id={name}
                value={typeof value === "string" ? value : ""}
                onChange={(e) => onChange(e.target.value)}
                placeholder={
                  typeof defaultValue === "string"
                    ? defaultValue
                    : `Enter ${name}`
                }
                rows={4}
                className="min-w-[300px] w-full"
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
              <Label htmlFor={name}>
                {name}
                {isRequired && <span className="text-destructive ml-1">*</span>}
              </Label>
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
            <Label htmlFor={name}>
              {name}
              {isRequired && <span className="text-destructive ml-1">*</span>}
            </Label>
            <Input
              id={name}
              type="number"
              step={type === "integer" ? "1" : "any"}
              value={typeof value === "number" ? value : ""}
              onChange={(e) => {
                const val =
                  type === "integer"
                    ? parseInt(e.target.value)
                    : parseFloat(e.target.value);
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
              <Label htmlFor={name}>
                {name}
                {isRequired && <span className="text-destructive ml-1">*</span>}
              </Label>
            </div>
            {description && (
              <p className="text-sm text-muted-foreground">{description}</p>
            )}
          </div>
        );

      case "array":
        return (
          <div className="space-y-2">
            <Label htmlFor={name}>
              {name}
              {isRequired && <span className="text-destructive ml-1">*</span>}
            </Label>
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
        return (
          <div className="space-y-2">
            <Label htmlFor={name}>
              {name}
              {isRequired && <span className="text-destructive ml-1">*</span>}
            </Label>
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
                  onChange(e.target.value);
                }
              }}
              placeholder='{"key": "value"}'
              rows={3}
              className="font-mono text-xs"
            />
            {description && (
              <p className="text-sm text-muted-foreground">{description}</p>
            )}
          </div>
        );
    }
  };

  return <div className={getFieldColumnSpan(name, schema)}>{renderInput()}</div>;
}

// ============================================================================
// Main Schema Form Renderer Component
// ============================================================================

export interface SchemaFormRendererProps {
  schema: JSONSchemaProperty;
  values: Record<string, unknown>;
  onChange: (values: Record<string, unknown>) => void;
  disabled?: boolean;
  readOnlyFields?: string[]; // NEW: Fields to display but not edit (for HIL)
  hideFields?: string[]; // NEW: Fields to completely hide
  showCollapsedByDefault?: boolean; // NEW: Control initial collapsed state
}

export function SchemaFormRenderer({
  schema,
  values,
  onChange,
  disabled = false,
  readOnlyFields = [],
  hideFields = [],
  showCollapsedByDefault = false,
}: SchemaFormRendererProps) {
  const [showAdvancedFields, setShowAdvancedFields] = useState(
    showCollapsedByDefault
  );

  const properties = schema.properties || {};
  const allFieldNames = Object.keys(properties).filter(
    (name) => !hideFields.includes(name)
  );
  const requiredFields = (schema.required || []).filter(
    (name) => !hideFields.includes(name)
  );

  // Detect ChatMessage pattern
  const isChatMessageLike = detectChatMessagePattern(schema, requiredFields);

  // Separate required and optional fields
  const requiredFieldNames = allFieldNames.filter(
    (name) =>
      requiredFields.includes(name) && !(isChatMessageLike && name === "role")
  );

  const optionalFieldNames = allFieldNames.filter(
    (name) => !requiredFields.includes(name)
  );

  // For ChatMessage: prioritize text/message/content
  const sortedOptionalFields = isChatMessageLike
    ? [...optionalFieldNames].sort((a, b) => {
        const priority = (name: string) =>
          ["text", "message", "content"].includes(name) ? 1 : 0;
        return priority(b) - priority(a);
      })
    : optionalFieldNames;

  // Show minimum visible fields
  const MIN_VISIBLE_FIELDS = isChatMessageLike ? 1 : 6;
  const visibleOptionalCount = Math.max(
    0,
    MIN_VISIBLE_FIELDS - requiredFieldNames.length
  );
  const visibleOptionalFields = sortedOptionalFields.slice(
    0,
    visibleOptionalCount
  );
  const collapsedOptionalFields = sortedOptionalFields.slice(
    visibleOptionalCount
  );

  const hasCollapsedFields = collapsedOptionalFields.length > 0;
  const hasRequiredFields = requiredFieldNames.length > 0;

  const updateField = (fieldName: string, value: unknown) => {
    onChange({
      ...values,
      [fieldName]: value,
    });
  };

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4 md:gap-6">
      {/* Required fields section */}
      {requiredFieldNames.map((fieldName) => (
        <FormField
          key={fieldName}
          name={fieldName}
          schema={properties[fieldName] as JSONSchemaProperty}
          value={values[fieldName]}
          onChange={(value) => updateField(fieldName, value)}
          isRequired={true}
          isReadOnly={disabled || readOnlyFields.includes(fieldName)}
        />
      ))}

      {/* Separator between required and optional */}
      {hasRequiredFields && optionalFieldNames.length > 0 && (
        <div className="md:col-span-2 lg:col-span-3 xl:col-span-4">
          <div className="border-t border-border"></div>
        </div>
      )}

      {/* Visible optional fields */}
      {visibleOptionalFields.map((fieldName) => (
        <FormField
          key={fieldName}
          name={fieldName}
          schema={properties[fieldName] as JSONSchemaProperty}
          value={values[fieldName]}
          onChange={(value) => updateField(fieldName, value)}
          isRequired={false}
          isReadOnly={disabled || readOnlyFields.includes(fieldName)}
        />
      ))}

      {/* Collapsed optional fields toggle */}
      {hasCollapsedFields && (
        <div className="md:col-span-2 lg:col-span-3 xl:col-span-4">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => setShowAdvancedFields(!showAdvancedFields)}
            className="w-full justify-center gap-2"
            disabled={disabled}
          >
            {showAdvancedFields ? (
              <>
                <ChevronUp className="h-4 w-4" />
                Hide {collapsedOptionalFields.length} optional field
                {collapsedOptionalFields.length !== 1 ? "s" : ""}
              </>
            ) : (
              <>
                <ChevronDown className="h-4 w-4" />
                Show {collapsedOptionalFields.length} optional field
                {collapsedOptionalFields.length !== 1 ? "s" : ""}
              </>
            )}
          </Button>
        </div>
      )}

      {/* Collapsed optional fields */}
      {showAdvancedFields &&
        collapsedOptionalFields.map((fieldName) => (
          <FormField
            key={fieldName}
            name={fieldName}
            schema={properties[fieldName] as JSONSchemaProperty}
            value={values[fieldName]}
            onChange={(value) => updateField(fieldName, value)}
            isRequired={false}
            isReadOnly={disabled || readOnlyFields.includes(fieldName)}
          />
        ))}
    </div>
  );
}

// ============================================================================
// Export helper functions for validation
// ============================================================================

export function validateSchemaForm(
  schema: JSONSchemaProperty,
  values: Record<string, unknown>
): boolean {
  const requiredFields = schema.required || [];

  return requiredFields.every((fieldName) => {
    const value = values[fieldName];
    return value !== undefined && value !== "" && value !== null;
  });
}

export function filterEmptyOptionalFields(
  schema: JSONSchemaProperty,
  values: Record<string, unknown>
): Record<string, unknown> {
  const requiredFields = schema.required || [];
  const filtered: Record<string, unknown> = {};

  Object.keys(values).forEach((key) => {
    const value = values[key];
    // Include if: 1) required field, OR 2) has non-empty value
    if (
      requiredFields.includes(key) ||
      (value !== undefined && value !== "" && value !== null)
    ) {
      filtered[key] = value;
    }
  });

  return filtered;
}
