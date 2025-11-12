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
import { Switch } from "@/components/ui/switch";
import { ExternalLink, RotateCcw, Info, ChevronRight } from "lucide-react";
import { useDevUIStore } from "@/stores";

interface SettingsModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onBackendUrlChange?: (url: string) => void;
}

type Tab = "general" | "proxy" | "about";

// Preset OpenAI models for quick selection
const PRESET_MODELS = [
  "gpt-4.1",
  "gpt-4.1-mini",
  "o1",
  "o1-mini",
  "o3-mini",
] as const;

export function SettingsModal({
  open,
  onOpenChange,
  onBackendUrlChange,
}: SettingsModalProps) {
  const [activeTab, setActiveTab] = useState<Tab>("general");

  // OpenAI proxy mode, Azure deployment, auth status, and server capabilities from store
  const { oaiMode, setOAIMode, azureDeploymentEnabled, setAzureDeploymentEnabled, authRequired, serverCapabilities } = useDevUIStore();

  // Get current backend URL from localStorage or default
  const defaultUrl = import.meta.env.VITE_API_BASE_URL !== undefined ? import.meta.env.VITE_API_BASE_URL : "";
  const [backendUrl, setBackendUrl] = useState(() => {
    return localStorage.getItem("devui_backend_url") || defaultUrl;
  });
  const [tempUrl, setTempUrl] = useState(backendUrl);

  // Auth token state
  const [authTokenStored, setAuthTokenStored] = useState(!!localStorage.getItem("devui_auth_token"));
  const [newAuthToken, setNewAuthToken] = useState("");

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

  const handleAuthTokenSave = () => {
    if (!newAuthToken.trim()) return;

    localStorage.setItem("devui_auth_token", newAuthToken.trim());
    setAuthTokenStored(true);
    setNewAuthToken("");

    // Reload to apply the auth token
    window.location.reload();
  };

  const handleClearAuthToken = () => {
    localStorage.removeItem("devui_auth_token");
    setAuthTokenStored(false);
    setNewAuthToken("");

    // Reload to clear auth state
    window.location.reload();
  };

  const isModified = tempUrl !== backendUrl;
  const isDefault = !localStorage.getItem("devui_backend_url");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[600px] max-w-[90vw] flex flex-col max-h-[85vh]">
        <DialogHeader className="p-6 pb-2 flex-shrink-0">
          <DialogTitle>Settings</DialogTitle>
        </DialogHeader>

        <DialogClose onClose={() => onOpenChange(false)} />

        {/* Tabs */}
        <div className="flex border-b px-6 flex-shrink-0">
          <button
            onClick={() => setActiveTab("general")}
            className={`px-4 py-2 text-sm font-medium transition-colors relative ${
              activeTab === "general"
                ? "text-foreground"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            General
            {activeTab === "general" && (
              <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary" />
            )}
          </button>
          {serverCapabilities.openai_proxy && (
            <button
              onClick={() => setActiveTab("proxy")}
              className={`px-4 py-2 text-sm font-medium transition-colors relative ${
                activeTab === "proxy"
                  ? "text-foreground"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              OpenAI Proxy
              {activeTab === "proxy" && (
                <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary" />
              )}
            </button>
          )}
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

        {/* Tab Content - Scrollable with min-height */}
        <div className="px-6 pb-6 overflow-y-auto flex-1 min-h-[400px]">
          {activeTab === "general" && (
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
                      <Button onClick={handleSave} size="sm" className="flex-1">
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

              {/* Auth Token Setting - Only show if backend requires auth OR token is already stored */}
              {(authRequired || authTokenStored) && (
                <div className="space-y-3 border-t pt-6">
                  <div className="flex items-center justify-between">
                    <Label className="text-sm font-medium">
                      Authentication Token
                    </Label>
                    {!authRequired && authTokenStored && (
                      <span className="text-xs text-muted-foreground">
                        (Not required by current backend)
                      </span>
                    )}
                  </div>

                  {authTokenStored ? (
                  <div className="space-y-3">
                    <div className="flex items-center gap-2">
                      <Input
                        type="password"
                        value="••••••••••••••••••••"
                        disabled
                        className="font-mono text-sm flex-1"
                      />
                      <Button
                        variant="destructive"
                        size="sm"
                        onClick={handleClearAuthToken}
                        className="flex-shrink-0"
                      >
                        Clear
                      </Button>
                    </div>
                    <p className="text-xs text-green-600 dark:text-green-400">
                      ✓ Token configured and stored locally
                    </p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    <Input
                      type="password"
                      value={newAuthToken}
                      onChange={(e) => setNewAuthToken(e.target.value)}
                      placeholder="Enter bearer token"
                      className="font-mono text-sm"
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && newAuthToken.trim()) {
                          handleAuthTokenSave();
                        }
                      }}
                    />
                    <Button
                      onClick={handleAuthTokenSave}
                      size="sm"
                      disabled={!newAuthToken.trim()}
                      className="w-full"
                    >
                      Save & Reload
                    </Button>
                    <p className="text-xs text-muted-foreground">
                      {authRequired
                        ? "Required by backend (started with --auth flag)"
                        : "Not required by current backend"}
                    </p>
                  </div>
                  )}
                </div>
              )}

              {/* Deployment Setting - Only show if backend supports deployment */}
              {serverCapabilities.deployment && (
              <div className="space-y-3 border-t pt-6">
                <div className="flex items-center justify-between">
                  <div className="space-y-0.5">
                    <Label className="text-sm font-medium">
                      Azure Deployment
                    </Label>
                    <p className="text-xs text-muted-foreground">
                      Enable one-click deployment to Azure Container Apps
                    </p>
                  </div>
                  <Switch
                    checked={azureDeploymentEnabled}
                    onCheckedChange={setAzureDeploymentEnabled}
                  />
                </div>

                {/* Expandable info section */}
                <details className="group">
                  <summary className="cursor-pointer text-xs text-muted-foreground hover:text-foreground transition-colors flex items-center gap-1">
                    <ChevronRight className="h-3 w-3 transition-transform group-open:rotate-90" />
                    Learn more about Azure deployment
                  </summary>
                  <div className="mt-3 space-y-3 pl-4">
                    <p className="text-xs text-muted-foreground leading-relaxed">
                      When enabled, agents that support deployment will show a "Deploy to Azure"
                      button. This allows you to deploy your agent to Azure Container Apps directly
                      from DevUI.
                    </p>

                    <div className="space-y-1.5">
                      <p className="text-xs font-medium">When enabled:</p>
                      <ul className="text-xs text-muted-foreground space-y-0.5 list-disc list-inside">
                        <li>Shows "Deploy to Azure" for supported agents</li>
                        <li>Requires Azure CLI and proper authentication</li>
                        <li>Backend must have deployment capabilities enabled</li>
                      </ul>
                    </div>

                    <div className="space-y-1.5">
                      <p className="text-xs font-medium">When disabled:</p>
                      <ul className="text-xs text-muted-foreground space-y-0.5 list-disc list-inside">
                        <li>Shows "Deployment Guide" for all agents</li>
                        <li>Provides Docker templates and manual deployment instructions</li>
                        <li>No backend deployment capabilities required</li>
                      </ul>
                    </div>
                  </div>
                </details>
              </div>
              )}
            </div>
          )}

          {activeTab === "proxy" && serverCapabilities.openai_proxy && (
            <div className="space-y-6 pt-4">
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <div className="space-y-0.5">
                    <Label className="text-base font-medium">
                      OpenAI Proxy Mode
                    </Label>
                    <p className="text-xs text-muted-foreground">
                      Route requests through DevUI backend to OpenAI API
                    </p>
                  </div>
                  <Switch
                    checked={oaiMode.enabled}
                    onCheckedChange={(checked: boolean) =>
                      setOAIMode({ ...oaiMode, enabled: checked })
                    }
                  />
                </div>

                {/* Info box when disabled - prominent */}
                {!oaiMode.enabled && (
                  <div className="bordder border-muted bg-muted/30 rounded-lg p-4 space-y-3">
                    <div className="flex items-start gap-2">
                      <Info className="h-4 w-4 flex-shrink-0 mt-0.5 text-blue-600 dark:text-blue-400" />
                      <div className="space-y-2">
                        <p className="text-sm font-medium">
                          About OpenAI Proxy Mode
                        </p>
                        <p className="text-xs text-muted-foreground leading-relaxed">
                          When enabled, your chat requests are sent to your
                          DevUI backend{" "}
                          <span className="font-mono font-semibold">
                            ({backendUrl})
                          </span>
                          , which then forwards them to OpenAI's API. This keeps
                          your{" "}
                          <span className="font-mono font-semibold">
                            OPENAI_API_KEY
                          </span>{" "}
                          secure on the server instead of exposing it in the
                          browser.
                        </p>

                        <div className="space-y-1.5 pt-1">
                          <p className="text-xs font-medium">Requirements:</p>
                          <ul className="text-xs text-muted-foreground space-y-0.5 list-disc list-inside">
                            <li>
                              Backend must have{" "}
                              <span className="font-mono">OPENAI_API_KEY</span>{" "}
                              configured
                            </li>
                            <li>
                              Backend must support OpenAI Responses API proxying
                              (DevUI does)
                            </li>
                          </ul>
                        </div>

                        <div className="space-y-1.5 pt-1">
                          <p className="text-xs font-medium">Why use this?</p>
                          <p className="text-xs text-muted-foreground">
                            Quickly test and compare OpenAI models directly
                            through the DevUI interface without creating custom
                            agents or exposing API keys in the browser.
                          </p>
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                {oaiMode.enabled && (
                  <div className="space-y-4 pl-4 border-l-2 border-muted">
                    {/* Model ID Input - Primary control */}
                    <div className="space-y-2">
                      <Label className="text-sm font-medium">Model</Label>
                      <Input
                        type="text"
                        value={oaiMode.model}
                        onChange={(e) =>
                          setOAIMode({ ...oaiMode, model: e.target.value })
                        }
                        placeholder="gpt-4.1-mini"
                        className="font-mono text-sm"
                      />
                      <p className="text-xs text-muted-foreground">
                        Enter any OpenAI model ID (e.g., gpt-4.1, o1, o3-mini)
                      </p>
                    </div>

                    {/* Quick Preset Buttons */}
                    <div className="space-y-2">
                      <Label className="text-xs text-muted-foreground">
                        Common presets
                      </Label>
                      <div className="flex flex-wrap gap-2">
                        {PRESET_MODELS.map((model) => (
                          <Button
                            key={model}
                            variant={
                              oaiMode.model === model ? "default" : "outline"
                            }
                            size="sm"
                            onClick={() => setOAIMode({ ...oaiMode, model })}
                            className="text-xs h-7"
                          >
                            {model}
                          </Button>
                        ))}
                      </div>
                    </div>

                    {/* Advanced Parameters */}
                    <details className="group">
                      <summary className="cursor-pointer text-sm font-medium text-muted-foreground hover:text-foreground transition-colors flex items-center gap-1">
                        <ChevronRight className="h-3 w-3 transition-transform group-open:rotate-90" />
                        Advanced Parameters (optional)
                      </summary>
                      <div className="space-y-3 mt-3 pl-4">
                        {/* Temperature */}
                        <div className="space-y-1">
                          <Label className="text-xs">Temperature</Label>
                          <Input
                            type="number"
                            step="0.1"
                            min="0"
                            max="2"
                            value={oaiMode.temperature ?? ""}
                            onChange={(e) =>
                              setOAIMode({
                                ...oaiMode,
                                temperature: e.target.value
                                  ? parseFloat(e.target.value)
                                  : undefined,
                              })
                            }
                            placeholder="1.0 (default)"
                            className="text-sm"
                          />
                          <p className="text-xs text-muted-foreground">
                            Controls randomness (0-2)
                          </p>
                        </div>

                        {/* Max Output Tokens */}
                        <div className="space-y-1">
                          <Label className="text-xs">Max Output Tokens</Label>
                          <Input
                            type="number"
                            min="1"
                            value={oaiMode.max_output_tokens ?? ""}
                            onChange={(e) =>
                              setOAIMode({
                                ...oaiMode,
                                max_output_tokens: e.target.value
                                  ? parseInt(e.target.value)
                                  : undefined,
                              })
                            }
                            placeholder="Auto"
                            className="text-sm"
                          />
                          <p className="text-xs text-muted-foreground">
                            Maximum tokens in response
                          </p>
                        </div>

                        {/* Top P */}
                        <div className="space-y-1">
                          <Label className="text-xs">Top P</Label>
                          <Input
                            type="number"
                            step="0.1"
                            min="0"
                            max="1"
                            value={oaiMode.top_p ?? ""}
                            onChange={(e) =>
                              setOAIMode({
                                ...oaiMode,
                                top_p: e.target.value
                                  ? parseFloat(e.target.value)
                                  : undefined,
                              })
                            }
                            placeholder="1.0 (default)"
                            className="text-sm"
                          />
                          <p className="text-xs text-muted-foreground">
                            Nucleus sampling (0-1)
                          </p>
                        </div>

                        {/* Reasoning Effort */}
                        <div className="space-y-1">
                          <Label className="text-xs">Reasoning Effort (o-series models)</Label>
                          <select
                            value={oaiMode.reasoning_effort ?? ""}
                            onChange={(e) =>
                              setOAIMode({
                                ...oaiMode,
                                reasoning_effort: e.target.value
                                  ? (e.target.value as "minimal" | "low" | "medium" | "high")
                                  : undefined,
                              })
                            }
                            className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                          >
                            <option value="">Auto (default)</option>
                            <option value="minimal">Minimal</option>
                            <option value="low">Low</option>
                            <option value="medium">Medium</option>
                            <option value="high">High</option>
                          </select>
                          <p className="text-xs text-muted-foreground">
                            Constrains reasoning effort (faster/cheaper vs thorough)
                          </p>
                        </div>
                      </div>
                    </details>
                  </div>
                )}
              </div>

              {/* Collapsed info at bottom when enabled */}
              {oaiMode.enabled && (
                <div className="flex items-start gap-2 text-xs text-muted-foreground bg-muted/50 p-3 rounded">
                  <Info className="h-3.5 w-3.5 flex-shrink-0 mt-0.5" />
                  <div className="space-y-1">
                    <p>
                      Requests route through{" "}
                      <span className="font-mono font-semibold">
                        {backendUrl}
                      </span>{" "}
                      to OpenAI API. Server must have{" "}
                      <span className="font-mono font-semibold">
                        OPENAI_API_KEY
                      </span>{" "}
                      configured.
                    </p>
                  </div>
                </div>
              )}
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
