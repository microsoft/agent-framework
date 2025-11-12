/**
 * DeploymentModal - Shows Azure deployment instructions and Docker templates
 * Features: Docker setup files, Azure Container Apps deployment guide
 */

import { useState, useEffect, useRef } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogClose,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Rocket,
  Container,
  Cloud,
  Copy,
  CheckCircle2,
  ExternalLink,
} from "lucide-react";

interface DeploymentModalProps {
  open: boolean;
  onClose: () => void;
  agentName?: string;
}

type Tab = "docker" | "azure";

export function DeploymentModal({
  open,
  onClose,
  agentName = "Agent",
}: DeploymentModalProps) {
  const [activeTab, setActiveTab] = useState<Tab>("docker");
  const [copiedTemplate, setCopiedTemplate] = useState<string | null>(null);
  const timeoutRef = useRef<NodeJS.Timeout | null>(null);

  // Cleanup timeout on unmount
  useEffect(() => {
    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, []);

  const handleCopy = async (template: string, templateName: string) => {
    try {
      await navigator.clipboard.writeText(template);
      setCopiedTemplate(templateName);

      // Clear any existing timeout
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }

      // Set new timeout with cleanup
      timeoutRef.current = setTimeout(() => {
        setCopiedTemplate(null);
        timeoutRef.current = null;
      }, 2000);
    } catch (err) {
      console.error("Failed to copy template:", err);
      // Reset state on error
      setCopiedTemplate(null);
    }
  };

  const dockerfileTemplate = `# Dockerfile for ${agentName}
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy agent/workflow directories
COPY . .

# Expose DevUI default port
EXPOSE 8080

# Run DevUI server
CMD ["devui", ".", "--port", "8080", "--host", "0.0.0.0"]
`;

  const dockerComposeTemplate = `# docker-compose.yml
version: '3.8'

services:
  ${agentName.toLowerCase().replace(/\s+/g, "-")}:
    build: .
    environment:
      # OpenAI
      - OPENAI_API_KEY=\${OPENAI_API_KEY}
      - OPENAI_CHAT_MODEL_ID=\${OPENAI_CHAT_MODEL_ID:-gpt-4o-mini}
      # Or Azure OpenAI
      - AZURE_OPENAI_API_KEY=\${AZURE_OPENAI_API_KEY}
      - AZURE_OPENAI_ENDPOINT=\${AZURE_OPENAI_ENDPOINT}
      - AZURE_OPENAI_CHAT_DEPLOYMENT_NAME=\${AZURE_OPENAI_CHAT_DEPLOYMENT_NAME}
      # Optional: Enable tracing
      - ENABLE_OTEL=\${ENABLE_OTEL:-false}
    ports:
      - "8080:8080"
    restart: unless-stopped
`;

  const requirementsTemplate = `# requirements.txt
agent-framework-devui>=0.1.0
agent-framework>=0.1.0
# Chat clients (install what you need)
openai>=1.0.0
# azure-openai
# anthropic
`;

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="w-[800px] max-w-[90vw]">
        <DialogClose onClose={onClose} />
        <DialogHeader className="p-6 pb-2">
          <DialogTitle className="flex items-center gap-2">
            <Rocket className="h-5 w-5" />
            Deploy {agentName}
          </DialogTitle>
          <p className="text-sm text-muted-foreground pt-1">
            Get started with containerizing your agent for deployment.
          </p>
        </DialogHeader>

        {/* Tabs */}
        <div className="flex border-b px-6">
          <button
            onClick={() => setActiveTab("docker")}
            className={`px-4 py-2 text-sm font-medium transition-colors relative ${
              activeTab === "docker"
                ? "text-foreground"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            <Container className="h-4 w-4 mr-2 inline" />
            Docker
            {activeTab === "docker" && (
              <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary" />
            )}
          </button>
          <button
            onClick={() => setActiveTab("azure")}
            className={`px-4 py-2 text-sm font-medium transition-colors relative ${
              activeTab === "azure"
                ? "text-foreground"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            <Cloud className="h-4 w-4 mr-2 inline" />
            Azure
            {activeTab === "azure" && (
              <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary" />
            )}
          </button>
        </div>

        {/* Tab Content */}
        <div className="px-6 pb-6 min-h-[400px]">
          <ScrollArea className="h-[500px]">
            <div className="pr-4">
              {activeTab === "docker" && (
                <div className="space-y-4 pt-4">
                  <div>
                    <h3 className="font-semibold mb-2">
                      Containerize with Docker
                    </h3>
                    <p className="text-sm text-muted-foreground">
                      Package your agent as a Docker container for consistent
                      deployment anywhere.
                    </p>
                  </div>

                  {/* Dockerfile */}
                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-sm font-medium">Dockerfile</span>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() =>
                          handleCopy(dockerfileTemplate, "dockerfile")
                        }
                      >
                        {copiedTemplate === "dockerfile" ? (
                          <>
                            <CheckCircle2 className="h-4 w-4 mr-1 text-green-500" />
                            Copied!
                          </>
                        ) : (
                          <>
                            <Copy className="h-4 w-4 mr-1" />
                            Copy
                          </>
                        )}
                      </Button>
                    </div>
                    <pre className="bg-muted p-3 rounded-md text-xs overflow-x-auto border">
                      {dockerfileTemplate}
                    </pre>
                  </div>

                  {/* docker-compose.yml */}
                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-sm font-medium">
                        docker-compose.yml
                      </span>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() =>
                          handleCopy(dockerComposeTemplate, "compose")
                        }
                      >
                        {copiedTemplate === "compose" ? (
                          <>
                            <CheckCircle2 className="h-4 w-4 mr-1 text-green-500" />
                            Copied!
                          </>
                        ) : (
                          <>
                            <Copy className="h-4 w-4 mr-1" />
                            Copy
                          </>
                        )}
                      </Button>
                    </div>
                    <pre className="bg-muted p-3 rounded-md text-xs overflow-x-auto border">
                      {dockerComposeTemplate}
                    </pre>
                  </div>

                  {/* requirements.txt */}
                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-sm font-medium">
                        requirements.txt
                      </span>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() =>
                          handleCopy(requirementsTemplate, "requirements")
                        }
                      >
                        {copiedTemplate === "requirements" ? (
                          <>
                            <CheckCircle2 className="h-4 w-4 mr-1 text-green-500" />
                            Copied!
                          </>
                        ) : (
                          <>
                            <Copy className="h-4 w-4 mr-1" />
                            Copy
                          </>
                        )}
                      </Button>
                    </div>
                    <pre className="bg-muted p-3 rounded-md text-xs overflow-x-auto border">
                      {requirementsTemplate}
                    </pre>
                  </div>

                  {/* Quick Start */}
                  <div className="bg-blue-50 dark:bg-blue-950/50 border border-blue-200 dark:border-blue-800 rounded-md p-3">
                    <h4 className="text-sm font-semibold mb-2">Quick Start</h4>
                    <ol className="text-xs space-y-1 list-decimal list-inside text-muted-foreground">
                      <li>Save the files above to your project directory</li>
                      <li>
                        Build:{" "}
                        <code className="bg-muted px-1 rounded">
                          docker build -t {agentName.toLowerCase()}-agent .
                        </code>
                      </li>
                      <li>
                        Run:{" "}
                        <code className="bg-muted px-1 rounded">
                          docker-compose up
                        </code>
                      </li>
                      <li>Your agent is now running in a container!</li>
                    </ol>
                  </div>

                  {/* Production Warnings */}
                  <div className="bg-amber-50 dark:bg-amber-950/50 border border-amber-200 dark:border-amber-800 rounded-md p-3">
                    <h4 className="text-sm font-semibold mb-2 text-amber-900 dark:text-amber-100">
                      ⚠️ Production Considerations
                    </h4>
                    <ul className="text-xs space-y-1 list-disc list-inside text-amber-800 dark:text-amber-200">
                      <li>
                        <strong>In-memory state:</strong> Conversations are lost
                        when container restarts
                      </li>
                      <li>
                        <strong>No authentication:</strong> Add reverse proxy
                        (nginx, Caddy) with auth for production
                      </li>
                      <li>
                        <strong>Security:</strong> Use Azure Key Vault for
                        secrets management
                      </li>
                      <li>
                        <strong>Scaling:</strong> Single instance only due to
                        in-memory conversation store
                      </li>
                    </ul>
                  </div>

                  {/* Deployment Checklist */}
                  <div className="border-t pt-4">
                    <h4 className="font-semibold text-sm mb-3">
                      Pre-Deployment Checklist
                    </h4>
                    <div className="space-y-2 text-sm">
                      <div className="flex items-start gap-2">
                        <CheckCircle2 className="h-4 w-4 mt-0.5 text-muted-foreground flex-shrink-0" />
                        <span className="text-muted-foreground">
                          Set environment variables (API keys, secrets)
                        </span>
                      </div>
                      <div className="flex items-start gap-2">
                        <CheckCircle2 className="h-4 w-4 mt-0.5 text-muted-foreground flex-shrink-0" />
                        <span className="text-muted-foreground">
                          Test agent locally in container
                        </span>
                      </div>
                      <div className="flex items-start gap-2">
                        <CheckCircle2 className="h-4 w-4 mt-0.5 text-muted-foreground flex-shrink-0" />
                        <span className="text-muted-foreground">
                          Configure logging and monitoring
                        </span>
                      </div>
                      <div className="flex items-start gap-2">
                        <CheckCircle2 className="h-4 w-4 mt-0.5 text-muted-foreground flex-shrink-0" />
                        <span className="text-muted-foreground">
                          Set up error handling and retries
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {activeTab === "azure" && (
                <div className="space-y-4 pt-4">
                  <div>
                    <h3 className="font-semibold mb-2">
                      Deploy to Azure Container Apps
                    </h3>
                    <p className="text-sm text-muted-foreground">
                      Azure Container Apps provides serverless containers with
                      auto-scaling and integrated monitoring.
                    </p>
                  </div>

                  {/* Prerequisites */}
                  <div className="border rounded-lg p-4 space-y-3">
                    <h4 className="font-medium text-sm">Prerequisites</h4>
                    <ul className="text-xs space-y-1 list-disc list-inside text-muted-foreground">
                      <li>Azure subscription</li>
                      <li>
                        Azure CLI installed (
                        <code className="bg-muted px-1 rounded">
                          az --version
                        </code>
                        )
                      </li>
                      <li>Docker installed and running</li>
                      <li>
                        Logged in to Azure:{" "}
                        <code className="bg-muted px-1 rounded">az login</code>
                      </li>
                    </ul>
                  </div>

                  {/* Step-by-step */}
                  <div className="space-y-3">
                    <h4 className="font-medium text-sm">Deployment Steps</h4>

                    <div className="space-y-3">
                      {/* Step 1 */}
                      <div className="border-l-2 border-primary pl-3">
                        <div className="flex items-center gap-2 mb-1">
                          <div className="w-5 h-5 rounded-full bg-primary text-primary-foreground flex items-center justify-center text-xs font-bold">
                            1
                          </div>
                          <h5 className="font-medium text-sm">
                            Create Azure Container Registry
                          </h5>
                        </div>
                        <pre className="bg-muted p-2 rounded text-xs overflow-x-auto border mt-2">
                          {`# Create resource group
az group create --name myResourceGroup --location eastus

# Create container registry
az acr create --resource-group myResourceGroup \\
  --name myregistry --sku Basic`}
                        </pre>
                      </div>

                      {/* Step 2 */}
                      <div className="border-l-2 border-primary pl-3">
                        <div className="flex items-center gap-2 mb-1">
                          <div className="w-5 h-5 rounded-full bg-primary text-primary-foreground flex items-center justify-center text-xs font-bold">
                            2
                          </div>
                          <h5 className="font-medium text-sm">
                            Build and Push Docker Image
                          </h5>
                        </div>
                        <pre className="bg-muted p-2 rounded text-xs overflow-x-auto border mt-2">
                          {`# Build and push in one command
az acr build --registry myregistry \\
  --image ${agentName.toLowerCase()}-agent:latest .`}
                        </pre>
                      </div>

                      {/* Step 3 */}
                      <div className="border-l-2 border-primary pl-3">
                        <div className="flex items-center gap-2 mb-1">
                          <div className="w-5 h-5 rounded-full bg-primary text-primary-foreground flex items-center justify-center text-xs font-bold">
                            3
                          </div>
                          <h5 className="font-medium text-sm">
                            Create Container Apps Environment
                          </h5>
                        </div>
                        <pre className="bg-muted p-2 rounded text-xs overflow-x-auto border mt-2">
                          {`az containerapp env create --name myEnvironment \\
  --resource-group myResourceGroup \\
  --location eastus`}
                        </pre>
                      </div>

                      {/* Step 4 */}
                      <div className="border-l-2 border-primary pl-3">
                        <div className="flex items-center gap-2 mb-1">
                          <div className="w-5 h-5 rounded-full bg-primary text-primary-foreground flex items-center justify-center text-xs font-bold">
                            4
                          </div>
                          <h5 className="font-medium text-sm">
                            Deploy Container App
                          </h5>
                        </div>
                        <pre className="bg-muted p-2 rounded text-xs overflow-x-auto border mt-2">
                          {`az containerapp create --name ${agentName.toLowerCase()}-app \\
  --resource-group myResourceGroup \\
  --environment myEnvironment \\
  --image myregistry.azurecr.io/${agentName.toLowerCase()}-agent:latest \\
  --target-port 8080 \\
  --ingress 'external' \\
  --registry-server myregistry.azurecr.io \\
  --env-vars OPENAI_API_KEY=secretref:openai-key OPENAI_CHAT_MODEL_ID=gpt-4o-mini`}
                        </pre>
                      </div>

                      {/* Step 5 */}
                      <div className="border-l-2 border-primary pl-3">
                        <div className="flex items-center gap-2 mb-1">
                          <div className="w-5 h-5 rounded-full bg-primary text-primary-foreground flex items-center justify-center text-xs font-bold">
                            5
                          </div>
                          <h5 className="font-medium text-sm">
                            Get Application URL
                          </h5>
                        </div>
                        <pre className="bg-muted p-2 rounded text-xs overflow-x-auto border mt-2">
                          {`az containerapp show --name ${agentName.toLowerCase()}-app \\
  --resource-group myResourceGroup \\
  --query properties.configuration.ingress.fqdn`}
                        </pre>
                      </div>
                    </div>
                  </div>

                  {/* Learn More */}
                  <div className="bg-blue-50 dark:bg-blue-950/50 border border-blue-200 dark:border-blue-800 rounded-md p-3">
                    <h4 className="text-sm font-semibold mb-2">Learn More</h4>
                    <p className="text-xs text-muted-foreground mb-3">
                      Explore Azure Container Apps documentation for advanced
                      features like scaling, monitoring, and CI/CD integration.
                    </p>
                    <Button
                      size="sm"
                      variant="outline"
                      className="w-full"
                      asChild
                    >
                      <a
                        href="https://learn.microsoft.com/azure/container-apps/"
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        <ExternalLink className="h-3 w-3 mr-1" />
                        View Azure Container Apps Documentation
                      </a>
                    </Button>
                  </div>
                </div>
              )}
            </div>
          </ScrollArea>
        </div>
      </DialogContent>
    </Dialog>
  );
}
