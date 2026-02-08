/**
 * SetupInstructionsModal - Shows step-by-step instructions for running a sample entity
 */

import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Download,
  ExternalLink,
  Copy,
  Check,
  Lightbulb,
  BookOpen,
} from "lucide-react";
import type { SampleEntity } from "@/data/gallery";

interface SetupInstructionsModalProps {
  sample: SampleEntity;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function CodeBlock({ children, copyable = false }: { children: string; copyable?: boolean }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(children);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="relative">
      <pre className="bg-muted p-3 rounded-md text-sm overflow-x-auto font-mono">
        <code>{children}</code>
      </pre>
      {copyable && (
        <Button
          variant="ghost"
          size="sm"
          className="absolute top-2 right-2 h-6 w-6 p-0"
          onClick={handleCopy}
        >
          {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
        </Button>
      )}
    </div>
  );
}

function SetupStep({
  number,
  title,
  description,
  code,
  action,
  copyable = false,
}: {
  number: number;
  title: string;
  description?: string;
  code?: string;
  action?: React.ReactNode;
  copyable?: boolean;
}) {
  return (
    <div className="flex gap-4">
      <div className="flex-shrink-0">
        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary text-primary-foreground font-semibold">
          {number}
        </div>
      </div>
      <div className="flex-1 space-y-2">
        <h4 className="font-semibold">{title}</h4>
        {description && <p className="text-sm text-muted-foreground">{description}</p>}
        {code && <CodeBlock copyable={copyable}>{code}</CodeBlock>}
        {action && <div>{action}</div>}
      </div>
    </div>
  );
}

export function SetupInstructionsModal({
  sample,
  open,
  onOpenChange,
}: SetupInstructionsModalProps) {
  const hasEnvVars = sample.requiredEnvVars && sample.requiredEnvVars.length > 0;
  const stepOffset = hasEnvVars ? 0 : -1;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader className="px-6 pt-6 pb-2">
          <DialogTitle>Setup: {sample.name}</DialogTitle>
          <DialogDescription>
            Follow these steps to run this sample {sample.type} locally
          </DialogDescription>
        </DialogHeader>

        <div className="px-6 pb-6">
          <ScrollArea className="h-[500px]">
            <div className="space-y-6 pr-4">
              {/* Step 1: Download */}
              <SetupStep
                number={1}
                title="Download the sample file"
                action={
                  <Button asChild size="sm">
                    <a
                      href={sample.url}
                      download={`${sample.id}.py`}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      <Download className="h-4 w-4 mr-2" />
                      Download {sample.id}.py
                    </a>
                  </Button>
                }
              />

              {/* Step 2: Create folder */}
              <SetupStep
                number={2}
                title="Create a project folder"
                description="Create a dedicated folder for this sample and move the downloaded file there:"
                code={`mkdir -p ~/my-agents/${sample.id}\nmv ~/Downloads/${sample.id}.py ~/my-agents/${sample.id}/`}
                copyable
              />

              {/* Step 3: Environment variables (conditional) */}
              {hasEnvVars && (
                <SetupStep
                  number={3}
                  title="Set up environment variables"
                  description="Create a .env file in the project folder with these required variables:"
                  code={sample.requiredEnvVars!
                    .map((v) => `${v.name}=${v.example || "your-value-here"}\n# ${v.description}`)
                    .join("\n\n")}
                  copyable
                />
              )}

              {/* Step 4: Run DevUI */}
              <SetupStep
                number={4 + stepOffset}
                title="Run with DevUI"
                description="Navigate to the folder and start DevUI:"
                code={`cd ~/my-agents/${sample.id}\ndevui .`}
                copyable
              />

              {/* Alternative: Direct run */}
              <Alert>
                <Lightbulb className="h-4 w-4" />
                <AlertTitle>Alternative: Run Programmatically</AlertTitle>
                <AlertDescription className="mt-2">
                  <p className="mb-2">You can also run the {sample.type} directly in Python:</p>
                  <CodeBlock copyable>
                    {`from ${sample.id} import ${sample.type}
import asyncio

async def main():
    response = await ${sample.type}.run("Hello!")
    print(response)

asyncio.run(main())`}
                  </CodeBlock>
                </AlertDescription>
              </Alert>

              {/* Help links */}
              <div className="flex gap-2 pt-4 border-t">
                <Button variant="outline" size="sm" asChild>
                  <a href={sample.url} target="_blank" rel="noopener noreferrer">
                    <ExternalLink className="h-4 w-4 mr-2" />
                    View Source
                  </a>
                </Button>
                <Button variant="outline" size="sm" asChild>
                  <a
                    href="https://github.com/microsoft/agent-framework#readme"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    <BookOpen className="h-4 w-4 mr-2" />
                    Documentation
                  </a>
                </Button>
              </div>
            </div>
          </ScrollArea>
        </div>
      </DialogContent>
    </Dialog>
  );
}
