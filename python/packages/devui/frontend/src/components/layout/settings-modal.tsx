/**
 * Settings Modal - Tabbed settings dialog with About and Settings tabs
 */

import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogClose,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ExternalLink, RotateCcw } from "lucide-react";

interface SettingsModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onBackendUrlChange?: (url: string) => void;
}

type Tab = "about" | "settings";

export function SettingsModal({ open, onOpenChange, onBackendUrlChange }: SettingsModalProps) {
  const [activeTab, setActiveTab] = useState<Tab>("settings");

  // Get current backend URL from localStorage or default
  const defaultUrl = import.meta.env.VITE_API_BASE_URL || "http://localhost:8080";
  const [backendUrl, setBackendUrl] = useState(() => {
    return localStorage.getItem("devui_backend_url") || defaultUrl;
  });
  const [tempUrl, setTempUrl] = useState(backendUrl);

  const handleSave = () => {
    // Validate URL format
    try {
      new URL(tempUrl);
      localStorage.setItem("devui_backend_url", tempUrl);
      setBackendUrl(tempUrl);
      onBackendUrlChange?.(tempUrl);
      onOpenChange(false);

      // Reload to apply new backend URL
      window.location.reload();
    } catch {
      alert("Please enter a valid URL (e.g., http://localhost:8080)");
    }
  };

  const handleReset = () => {
    localStorage.removeItem("devui_backend_url");
    setTempUrl(defaultUrl);
    setBackendUrl(defaultUrl);
    onBackendUrlChange?.(defaultUrl);

    // Reload to apply default backend URL
    window.location.reload();
  };

  const isModified = tempUrl !== backendUrl;
  const isDefault = !localStorage.getItem("devui_backend_url");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[600px] max-w-[90vw]">
        <DialogHeader className="p-6 pb-2">
          <DialogTitle>Settings</DialogTitle>
        </DialogHeader>

        <DialogClose onClose={() => onOpenChange(false)} />

        {/* Tabs */}
        <div className="flex border-b px-6">
          <button
            onClick={() => setActiveTab("settings")}
            className={`px-4 py-2 text-sm font-medium transition-colors relative ${
              activeTab === "settings"
                ? "text-foreground"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            Settings
            {activeTab === "settings" && (
              <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary" />
            )}
          </button>
          <button
            onClick={() => setActiveTab("about")}
            className={`px-4 py-2 text-sm font-medium transition-colors relative ${
              activeTab === "about"
                ? "text-foreground"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            About
            {activeTab === "about" && (
              <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary" />
            )}
          </button>
        </div>

        {/* Tab Content */}
        <div className="px-6 pb-6 min-h-[240px]">
          {activeTab === "settings" && (
            <div className="space-y-6 pt-4">
              {/* Backend URL Setting */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <Label htmlFor="backend-url" className="text-sm font-medium">
                    Backend URL
                  </Label>
                  {!isDefault && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={handleReset}
                      className="h-7 text-xs"
                      title="Reset to default"
                    >
                      <RotateCcw className="h-3 w-3 mr-1" />
                      Reset
                    </Button>
                  )}
                </div>

                <Input
                  id="backend-url"
                  type="url"
                  value={tempUrl}
                  onChange={(e) => setTempUrl(e.target.value)}
                  placeholder="http://localhost:8080"
                  className="font-mono text-sm"
                />

                <p className="text-xs text-muted-foreground">
                  Default: <span className="font-mono">{defaultUrl}</span>
                </p>

                {/* Reserve space for buttons to prevent layout shift */}
                <div className="flex gap-2 pt-2 min-h-[36px]">
                  {isModified && (
                    <>
                      <Button
                        onClick={handleSave}
                        size="sm"
                        className="flex-1"
                      >
                        Apply & Reload
                      </Button>
                      <Button
                        onClick={() => setTempUrl(backendUrl)}
                        variant="outline"
                        size="sm"
                        className="flex-1"
                      >
                        Cancel
                      </Button>
                    </>
                  )}
                </div>
              </div>
            </div>
          )}

          {activeTab === "about" && (
            <div className="space-y-4 pt-4">
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
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
