/**
 * HilTimelineItem - Inline HIL request form for the ExecutionTimeline
 * Shows HIL requests as part of the workflow execution flow
 */

import { useState } from "react";
import { Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { SchemaFormRenderer, validateSchemaForm } from "./schema-form-renderer";
import type { JSONSchemaProperty } from "@/types";

export interface HilRequest {
  request_id: string;
  request_data: Record<string, unknown>;
  request_schema: JSONSchemaProperty;
}

interface HilTimelineItemProps {
  request: HilRequest;
  response: Record<string, unknown>;
  onResponseChange: (values: Record<string, unknown>) => void;
  onSubmit: () => void;
  isSubmitting: boolean;
}

export function HilTimelineItem({
  request,
  response,
  onResponseChange,
  onSubmit,
  isSubmitting,
}: HilTimelineItemProps) {
  const [isExpanded, setIsExpanded] = useState(true);

  const handleResponseChange = (values: Record<string, unknown>) => {
    onResponseChange(values);
  };

  const isValid = validateSchemaForm(request.request_schema, response);

  return (
    <div className="relative group">
      {/* Main content - removed icon and adjusted layout */}
      <div>
        {/* Content area - removed pb-4 padding */}
        <div className="flex-1">
          <div className="border border-orange-200 dark:border-orange-800 bg-orange-50/50 dark:bg-orange-950/20 overflow-hidden rounded-lg">
            {/* Header */}
            <div
              className="px-4 py-3 bg-orange-100/50 dark:bg-orange-950/30 border-b border-orange-200 dark:border-orange-800 flex items-center justify-between cursor-pointer hover:bg-orange-100 dark:hover:bg-orange-950/40 transition-colors"
              onClick={() => setIsExpanded(!isExpanded)}
            >
              <div className="flex items-center gap-2">
                <span className="font-medium text-sm text-orange-900 dark:text-orange-100">
                  Workflow needs your input
                </span>
                <Badge
                  variant="outline"
                  className="text-xs font-mono border-orange-300 dark:border-orange-700 text-orange-700 dark:text-orange-300"
                >
                  {request.request_id.slice(0, 8)}
                </Badge>
                {!isExpanded && (
                  <span className="text-xs text-orange-600 dark:text-orange-400 animate-pulse">
                    Click to respond
                  </span>
                )}
              </div>
              {isSubmitting && (
                <Badge variant="secondary" className="animate-pulse">
                  Submitting...
                </Badge>
              )}
            </div>

            {/* Expanded content */}
            {isExpanded && (
              <div className="p-4 space-y-4">
                {/* Request context - scrollable */}
                {Object.keys(request.request_data).length > 0 && (
                  <div className="bg-white/60 dark:bg-gray-900/30 rounded-md p-3 space-y-2">
                    <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                      Context
                    </p>
                    <div className="max-h-48 overflow-y-auto space-y-1 pr-2">
                      {Object.entries(request.request_data)
                        .filter(
                          ([key]) =>
                            !["request_id", "source_executor_id"].includes(key)
                        )
                        .map(([key, value]) => (
                          <div key={key} className="text-sm">
                            <span className="font-medium text-muted-foreground">
                              {key}:
                            </span>{" "}
                            <span className="text-foreground break-all">
                              {typeof value === "object"
                                ? JSON.stringify(value, null, 2)
                                : String(value)}
                            </span>
                          </div>
                        ))}
                    </div>
                  </div>
                )}

                {/* Description hint */}
                {request.request_schema?.description && (
                  <div className="text-sm text-muted-foreground bg-blue-50 dark:bg-blue-950/20 p-3 rounded-md border border-blue-200 dark:border-blue-800">
                    <p className="font-medium text-blue-900 dark:text-blue-100 mb-1">
                      What's needed:
                    </p>
                    <p className="text-blue-800 dark:text-blue-200">
                      {request.request_schema.description}
                    </p>
                  </div>
                )}

                {/* Input form */}
                <div className="space-y-3">
                  <SchemaFormRenderer
                    schema={request.request_schema}
                    values={response}
                    onChange={handleResponseChange}
                  />
                </div>

                {/* Actions */}
                <div className="space-y-2 pt-2">
                  <Button
                    size="default"
                    onClick={onSubmit}
                    disabled={!isValid || isSubmitting}
                    className="w-full gap-2"
                  >
                    <Send className="w-4 h-4" />
                    Submit Response
                  </Button>
                  {!isValid && (
                    <div className="text-xs text-muted-foreground text-center">
                      Please fill in all required fields
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
