/**
 * About DevUI Modal - Shows information about the DevUI sample app
 */

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogClose,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { ExternalLink } from "lucide-react";

interface AboutModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function AboutModal({ open, onOpenChange }: AboutModalProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>About DevUI</DialogTitle>
          <DialogClose onClose={() => onOpenChange(false)} />
        </DialogHeader>

        <div className="p-4 space-y-4">
          <p className="text-sm text-muted-foreground">
            DevUI is a sample app for getting started with Agent Framework.
          </p>

          <div className="flex justify-center pt-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() =>
                window.open(
                  "https://github.com/microsoft/agent-framework",
                  "_blank"
                )
              }
              className="text-xs"
            >
              <ExternalLink className="h-3 w-3 mr-1" />
              Learn More about Agent Framework
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
