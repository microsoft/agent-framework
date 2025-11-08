import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { MessageCircle, Send, Loader2 } from "lucide-react";
import { SchemaFormRenderer, validateSchemaForm } from "./schema-form-renderer";
import type { JSONSchemaProperty } from "@/types";

interface HilRequest {
  request_id: string;
  request_data: Record<string, unknown>;
  request_schema: JSONSchemaProperty;
}

interface HilInputModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  requests: HilRequest[];
  responses: Record<string, Record<string, unknown>>;
  onResponseChange: (requestId: string, values: Record<string, unknown>) => void;
  onSubmit: () => void;
  isSubmitting: boolean;
}

export function HilInputModal({
  open,
  onOpenChange,
  requests,
  responses,
  onResponseChange,
  onSubmit,
  isSubmitting,
}: HilInputModalProps) {
  // Check if all required fields are filled
  const areAllRequiredFieldsFilled = () => {
    return requests.every((req) => {
      const response = responses[req.request_id] || {};
      return validateSchemaForm(req.request_schema, response);
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[80vh] overflow-y-auto">
        <DialogHeader className="px-6 pt-6 pb-4">
          <DialogTitle className="flex items-center gap-2">
            <MessageCircle className="w-5 h-5" />
            Workflow Requires Input ({requests.length} request
            {requests.length > 1 ? "s" : ""})
          </DialogTitle>
          <DialogDescription>
            The workflow is paused and needs your input to continue.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6">
          {requests.map((req, index) => (
            <Card key={req.request_id}>
              <CardHeader>
                <CardTitle className="text-sm flex items-center gap-2">
                  Request {index + 1}
                  <Badge variant="outline" className="ml-2 font-mono text-xs">
                    {req.request_id.slice(0, 8)}
                  </Badge>
                </CardTitle>
              </CardHeader>
              <CardContent>
                {/* Show request data as readonly context */}
                {Object.keys(req.request_data).length > 0 && (
                  <div className="mb-4 p-3 bg-muted rounded-md max-h-48 overflow-y-auto">
                    <p className="text-xs font-medium text-muted-foreground mb-2">
                      Request Context:
                    </p>
                    <div className="space-y-1">
                      {Object.entries(req.request_data)
                        .filter(([key]) => !["request_id", "source_executor_id"].includes(key))
                        .map(([key, value]) => (
                          <div key={key} className="text-xs">
                            <span className="font-medium">{key}:</span>{" "}
                            <span className="text-muted-foreground break-all">
                              {typeof value === "object" ? JSON.stringify(value) : String(value)}
                            </span>
                          </div>
                        ))}
                    </div>
                  </div>
                )}

                {/* Show expected response hint if available */}
                {req.request_schema?.description && (
                  <div className="mb-4 p-3 bg-blue-50 dark:bg-blue-950/30 border border-blue-200 dark:border-blue-800 rounded-md">
                    <p className="text-xs font-medium text-blue-900 dark:text-blue-100 mb-1">
                      Expected Response:
                    </p>
                    <p className="text-xs text-blue-700 dark:text-blue-300">
                      {req.request_schema.description}
                    </p>
                  </div>
                )}

                {/* Use schema-based form renderer for RESPONSE (not request) */}
                <SchemaFormRenderer
                  schema={req.request_schema}
                  values={responses[req.request_id] || {}}
                  onChange={(values) => onResponseChange(req.request_id, values)}
                  disabled={isSubmitting}
                />
              </CardContent>
            </Card>
          ))}
        </div>

        <DialogFooter>
          <div className="flex gap-2 w-full justify-end">
            <Button
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={isSubmitting}
            >
              Cancel
            </Button>
            <Button
              onClick={onSubmit}
              disabled={isSubmitting || !areAllRequiredFieldsFilled()}
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin mr-2" />
                  Submitting...
                </>
              ) : (
                <>
                  <Send className="w-4 h-4 mr-2" />
                  Submit & Continue
                </>
              )}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
