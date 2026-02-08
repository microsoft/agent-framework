/**
 * Sample entities for the gallery - curated examples to help users learn Agent Framework
 */

export interface EnvVarRequirement {
  name: string;
  description: string;
  required: boolean;
  example?: string;
}

export interface SampleEntity {
  id: string;
  name: string;
  description: string;
  type: "agent" | "workflow";
  url: string;
  tags: string[];
  author: string;
  difficulty: "beginner" | "intermediate" | "advanced";
  features: string[];
  requiredEnvVars?: EnvVarRequirement[];
}

export const SAMPLE_ENTITIES: SampleEntity[] = [
  // Beginner Agents
  {
    id: "foundry-weather-agent",
    name: "Azure AI Weather Agent",
    description:
      "Weather agent using Azure AI Agent (Foundry) with Azure CLI authentication",
    type: "agent",
    url: "https://raw.githubusercontent.com/microsoft/agent-framework/main/python/samples/getting_started/devui/foundry_agent/agent.py",
    tags: ["azure-ai", "foundry", "tools"],
    author: "Microsoft",
    difficulty: "beginner",
    features: [
      "Azure AI Agent integration",
      "Azure CLI authentication",
      "Mock weather tools",
    ],
    requiredEnvVars: [
      {
        name: "AZURE_AI_PROJECT_ENDPOINT",
        description: "Azure AI Foundry project endpoint URL",
        required: true,
        example: "https://your-project.api.azureml.ms",
      },
      {
        name: "FOUNDRY_MODEL_DEPLOYMENT_NAME",
        description: "Name of the deployed model in Azure AI Foundry",
        required: true,
        example: "gpt-4o",
      },
    ],
  },

  {
    id: "weather-agent-azure",
    name: "Azure OpenAI Weather Agent",
    description:
      "Weather agent using Azure OpenAI with API key authentication",
    type: "agent",
    url: "https://raw.githubusercontent.com/microsoft/agent-framework/main/python/samples/getting_started/devui/weather_agent_azure/agent.py",
    tags: ["azure", "openai", "tools"],
    author: "Microsoft",
    difficulty: "beginner",
    features: [
      "Azure OpenAI integration",
      "API key authentication",
      "Function calling",
      "Mock weather tools",
    ],
    requiredEnvVars: [
      {
        name: "AZURE_OPENAI_API_KEY",
        description: "Azure OpenAI API key",
        required: true,
      },
      {
        name: "AZURE_OPENAI_CHAT_DEPLOYMENT_NAME",
        description: "Name of the deployed model in Azure OpenAI",
        required: true,
        example: "gpt-4o",
      },
      {
        name: "AZURE_OPENAI_ENDPOINT",
        description: "Azure OpenAI endpoint URL",
        required: true,
        example: "https://your-resource.openai.azure.com",
      },
    ],
  },

  // Beginner Workflows
  {
    id: "spam-workflow",
    name: "Spam Detection Workflow",
    description:
      "5-step workflow demonstrating email spam detection with branching logic",
    type: "workflow",
    url: "https://raw.githubusercontent.com/microsoft/agent-framework/main/python/samples/getting_started/devui/spam_workflow/workflow.py",
    tags: ["workflow", "branching", "multi-step"],
    author: "Microsoft",
    difficulty: "beginner",
    features: [
      "Sequential execution",
      "Conditional branching",
      "Mock spam detection",
    ],
  },

  // Advanced Workflows
  {
    id: "fanout-workflow",
    name: "Complex Fan-In/Fan-Out Workflow",
    description:
      "Advanced data processing workflow with parallel validation, transformation, and quality assurance stages",
    type: "workflow",
    url: "https://raw.githubusercontent.com/microsoft/agent-framework/main/python/samples/getting_started/devui/fanout_workflow/workflow.py",
    tags: ["workflow", "fan-out", "fan-in", "parallel"],
    author: "Microsoft",
    difficulty: "advanced",
    features: [
      "Fan-out pattern",
      "Parallel execution",
      "Complex state management",
      "Multi-stage processing",
    ],
  },
];

// Group samples by category for better organization
export const SAMPLE_CATEGORIES = {
  all: SAMPLE_ENTITIES,
  agents: SAMPLE_ENTITIES.filter((e) => e.type === "agent"),
  workflows: SAMPLE_ENTITIES.filter((e) => e.type === "workflow"),
  beginner: SAMPLE_ENTITIES.filter((e) => e.difficulty === "beginner"),
  intermediate: SAMPLE_ENTITIES.filter((e) => e.difficulty === "intermediate"),
  advanced: SAMPLE_ENTITIES.filter((e) => e.difficulty === "advanced"),
};

// Get difficulty color for badges
export const getDifficultyColor = (difficulty: SampleEntity["difficulty"]) => {
  switch (difficulty) {
    case "beginner":
      return "bg-green-100 text-green-700 border-green-200";
    case "intermediate":
      return "bg-yellow-100 text-yellow-700 border-yellow-200";
    case "advanced":
      return "bg-red-100 text-red-700 border-red-200";
    default:
      return "bg-gray-100 text-gray-700 border-gray-200";
  }
};
