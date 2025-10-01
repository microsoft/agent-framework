/**
 * GalleryView - Consolidated gallery component with card and grid logic
 * Supports inline (empty state) and modal variants
 */

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Bot,
  Workflow,
  Plus,
  Loader2,
  User,
  TriangleAlert,
  AlertCircle,
  X,
  Key,
  ChevronDown,
  ArrowLeft,
} from "lucide-react";
import { cn } from "@/lib/utils";
import {
  SAMPLE_ENTITIES,
  type SampleEntity,
  getDifficultyColor,
} from "@/data/gallery";

interface GalleryViewProps {
  onAdd: (sample: SampleEntity) => Promise<void>;
  addingEntityId?: string | null;
  errorEntityId?: string | null;
  errorMessage?: string | null;
  onClearError?: (sampleId: string) => void;
  onClose?: () => void;
  variant?: "inline" | "route" | "modal";
  hasExistingEntities?: boolean;
}

// Internal: Sample Entity Card Component
function SampleEntityCard({
  sample,
  onAdd,
  isAdding = false,
  hasError = false,
  errorMessage,
  onClearError,
}: {
  sample: SampleEntity;
  onAdd: (sample: SampleEntity) => Promise<void>;
  isAdding?: boolean;
  hasError?: boolean;
  errorMessage?: string | null;
  onClearError?: (sampleId: string) => void;
}) {
  const [isLoading, setIsLoading] = useState(false);

  const handleAdd = async () => {
    if (isLoading || isAdding) return;

    setIsLoading(true);
    try {
      await onAdd(sample);
    } finally {
      setIsLoading(false);
    }
  };

  const TypeIcon = sample.type === "workflow" ? Workflow : Bot;
  const isDisabled = isLoading || isAdding;

  return (
    <Card
      className={cn(
        "hover:shadow-md transition-shadow duration-200 h-full flex flex-col overflow-hidden w-full",
        hasError && "border-destructive"
      )}
    >
      <CardHeader className="pb-3 min-w-0">
        <div className="flex items-start justify-between mb-2">
          <div className="flex items-center gap-2">
            <TypeIcon className="h-5 w-5" />
            <Badge variant="secondary" className="text-xs">
              {sample.type}
            </Badge>
          </div>
          <Badge
            variant="outline"
            className={cn(
              "text-xs border",
              getDifficultyColor(sample.difficulty)
            )}
          >
            {sample.difficulty}
          </Badge>
        </div>

        <CardTitle className="text-lg leading-tight">{sample.name}</CardTitle>
        <CardDescription className="text-sm line-clamp-3">
          {sample.description}
        </CardDescription>
      </CardHeader>

      <CardContent className="pt-0 flex-1 min-w-0 overflow-hidden">
        {/* Error Banner */}
        {hasError && errorMessage && (
          <div className="mb-3 p-3 bg-destructive/10 border border-destructive/20 rounded-md">
            <div className="flex items-start gap-2">
              <AlertCircle className="h-4 w-4 text-destructive flex-shrink-0 mt-0.5" />
              <div className="flex-1 min-w-0">
                <p className="text-xs text-destructive font-medium mb-1">
                  Failed to add
                </p>
                <p className="text-xs text-muted-foreground">{errorMessage}</p>
              </div>
              {onClearError && (
                <button
                  onClick={() => onClearError(sample.id)}
                  className="text-muted-foreground hover:text-foreground"
                  aria-label="Dismiss error"
                >
                  <X className="h-3 w-3" />
                </button>
              )}
            </div>
          </div>
        )}

        <div className="space-y-3 min-w-0">
          {/* Tags */}
          <div className="flex flex-wrap gap-1">
            {sample.tags.slice(0, 3).map((tag) => (
              <Badge key={tag} variant="outline" className="text-xs">
                {tag}
              </Badge>
            ))}
            {sample.tags.length > 3 && (
              <Badge variant="outline" className="text-xs">
                +{sample.tags.length - 3}
              </Badge>
            )}
          </div>

          {/* Environment Variables Required - Collapsible */}
          {sample.requiredEnvVars && sample.requiredEnvVars.length > 0 && (
            <details className="group min-w-0 max-w-full overflow-hidden">
              <summary className="cursor-pointer list-none p-2 bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800 rounded-md hover:bg-amber-100 dark:hover:bg-amber-950/30 transition-colors flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 min-w-0">
                  <Key className="h-3.5 w-3.5 text-amber-600 dark:text-amber-500 flex-shrink-0" />
                  <span className="text-xs font-medium text-amber-900 dark:text-amber-100 truncate">
                    Requires {sample.requiredEnvVars.length} env var
                    {sample.requiredEnvVars.length > 1 ? "s" : ""}
                  </span>
                </div>
                <ChevronDown className="h-3 w-3 text-amber-600 dark:text-amber-500 flex-shrink-0 group-open:rotate-180 transition-transform" />
              </summary>
              <div className="mt-2 p-2 bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800 rounded-md space-y-2 min-w-0 max-w-full overflow-hidden">
                {sample.requiredEnvVars.map((envVar) => (
                  <div key={envVar.name} className="text-xs min-w-0 max-w-full overflow-hidden">
                    <div className="font-mono font-medium text-amber-900 dark:text-amber-100 break-words">
                      {envVar.name}
                    </div>
                    <div className="text-amber-700 dark:text-amber-300 mt-0.5 break-words">
                      {envVar.description}
                    </div>
                    {envVar.example && (
                      <div className="font-mono text-amber-600 dark:text-amber-400 mt-0.5 break-all">
                        {envVar.example}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </details>
          )}

          {/* Features */}
          <div className="space-y-2">
            <div className="text-xs font-medium text-muted-foreground">
              Key Features:
            </div>
            <ul className="text-xs space-y-1">
              {sample.features.slice(0, 3).map((feature) => (
                <li key={feature} className="flex items-center gap-1">
                  <div className="w-1 h-1 rounded-full bg-current opacity-50" />
                  <span>{feature}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </CardContent>

      <CardFooter className="pt-3 flex-col gap-3">
        {/* Metadata */}
        <div className="w-full flex items-center justify-between text-xs text-muted-foreground">
          <div className="flex items-center gap-1">
            <User className="h-3 w-3" />
            <span>{sample.author}</span>
          </div>
        </div>

        {/* Add Button - Full width on its own line */}
        <Button
          onClick={handleAdd}
          disabled={isDisabled}
          className="w-full"
          size="sm"
          variant={hasError ? "outline" : "default"}
        >
          {isDisabled ? (
            <>
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              Adding...
            </>
          ) : hasError ? (
            <>
              <Plus className="h-4 w-4 mr-2" />
              Retry
            </>
          ) : (
            <>
              <Plus className="h-4 w-4 mr-2" />
              Add Sample
            </>
          )}
        </Button>
      </CardFooter>
    </Card>
  );
}

// Internal: Sample Entity Grid Component
function SampleEntityGrid({
  samples,
  onAdd,
  addingEntityId,
  errorEntityId,
  errorMessage,
  onClearError,
}: {
  samples: SampleEntity[];
  onAdd: (sample: SampleEntity) => Promise<void>;
  addingEntityId?: string | null;
  errorEntityId?: string | null;
  errorMessage?: string | null;
  onClearError?: (sampleId: string) => void;
}) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
      {samples.map((sample) => (
        <div key={sample.id} className="min-w-0">
          <SampleEntityCard
            sample={sample}
            onAdd={onAdd}
            isAdding={addingEntityId === sample.id}
            hasError={errorEntityId === sample.id}
            errorMessage={errorMessage}
            onClearError={onClearError}
          />
        </div>
      ))}
    </div>
  );
}

// Main: Gallery View Component
export function GalleryView({
  onAdd,
  addingEntityId,
  errorEntityId,
  errorMessage,
  onClearError,
  onClose,
  variant = "inline",
  hasExistingEntities = false,
}: GalleryViewProps) {
  // Inline variant - for empty state in main app
  if (variant === "inline") {
    return (
      <div className="flex-1 overflow-auto">
        <div className="max-w-7xl mx-auto px-6 py-8">
          {/* Info Banner */}
          <div className="mb-8 p-4 bg-muted/50 border border-border rounded-lg">
            <div className="flex items-start gap-3">
              <TriangleAlert className="h-5 w-5 text-amber-500 flex-shrink-0 mt-0.5" />
              <div className="flex-1">
                <h3 className="font-semibold mb-1">
                  No agents or workflows configured yet!
                </h3>
                <p className="text-sm text-muted-foreground mb-2">
                  You can configure agents or workflows by running{" "}
                  <code className="px-1.5 py-0.5 bg-background rounded text-xs">
                    devui
                  </code>{" "}
                  in a directory containing them.
                </p>
                <p className="text-sm text-muted-foreground">
                  You can also import any of the sample agents and workflows
                  below to get started quickly.
                </p>
              </div>
            </div>
          </div>

          {/* Sample Gallery */}
          <div className="mb-6">
            <h3 className="text-lg font-semibold mb-4">Sample Gallery</h3>
            <SampleEntityGrid
              samples={SAMPLE_ENTITIES}
              onAdd={onAdd}
              addingEntityId={addingEntityId}
              errorEntityId={errorEntityId}
              errorMessage={errorMessage}
              onClearError={onClearError}
            />
          </div>

          {/* Footer */}
          <div className="text-center mt-12 pt-8 border-t">
            <p className="text-sm text-muted-foreground">
              Want to create your own agents or workflows? Check out the{" "}
              <a
                href="https://github.com/microsoft/agent-framework"
                className="text-primary hover:underline"
                target="_blank"
                rel="noopener noreferrer"
              >
                documentation
              </a>
            </p>
          </div>
        </div>
      </div>
    );
  }

  // Route variant - for /gallery page
  if (variant === "route") {
    return (
      <div className="h-full overflow-auto">
        <div className="max-w-7xl mx-auto px-6 py-8">
          {/* Header */}
          <div className="mb-8">
            {hasExistingEntities && (
              <div className="mb-4">
                <Button variant="ghost" onClick={onClose} className="gap-2">
                  <ArrowLeft className="h-4 w-4" />
                  Back
                </Button>
              </div>
            )}

            <div className="text-center">
              <h2 className="text-2xl font-semibold mb-2">Sample Gallery</h2>
              <p className="text-muted-foreground max-w-2xl mx-auto">
                Browse and add sample agents and workflows to learn the Agent
                Framework. These are curated examples ranging from beginner to
                advanced.
              </p>
            </div>
          </div>

          {/* Sample Gallery */}
          <SampleEntityGrid
            samples={SAMPLE_ENTITIES}
            onAdd={onAdd}
            addingEntityId={addingEntityId}
            errorEntityId={errorEntityId}
            errorMessage={errorMessage}
            onClearError={onClearError}
          />

          {/* Footer */}
          <div className="text-center mt-12 pt-8 border-t">
            <p className="text-sm text-muted-foreground">
              Want to create your own agents or workflows? Check out the{" "}
              <a
                href="https://github.com/microsoft/agent-framework"
                className="text-primary hover:underline"
                target="_blank"
                rel="noopener noreferrer"
              >
                documentation
              </a>
            </p>
          </div>
        </div>
      </div>
    );
  }

  // Modal variant - for dropdown trigger (simplified, just the grid)
  return (
    <SampleEntityGrid
      samples={SAMPLE_ENTITIES}
      onAdd={onAdd}
      addingEntityId={addingEntityId}
      errorEntityId={errorEntityId}
      errorMessage={errorMessage}
      onClearError={onClearError}
    />
  );
}
