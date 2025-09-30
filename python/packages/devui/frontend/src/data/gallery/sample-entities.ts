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
    id: "basic-foundry-agent",
    name: "Basic Foundry Agent",
    description:
      "Simple conversational AI agent using Azure OpenAI Foundry models",
    type: "agent",
    url: "https://raw.githubusercontent.com/victordibia/designing-multiagent-systems/refs/heads/main/course/samples/hello_world/agent_framework/agent.py",
    tags: ["foundry", "conversation", "basic"],
    author: "Microsoft",
    difficulty: "beginner",
    features: [
      "Basic conversation",
      "Azure OpenAI integration",
      "Simple setup",
    ],
    requiredEnvVars: [
      {
        name: "AZURE_OPENAI_ENDPOINT",
        description: "Azure OpenAI service endpoint URL",
        required: true,
        example: "https://your-resource.openai.azure.com/",
      },
      {
        name: "AZURE_OPENAI_API_KEY",
        description: "API key for Azure OpenAI service",
        required: true,
      },
    ],
  },

  {
    id: "foundry-with-thread",
    name: "Foundry Agent with Memory",
    description:
      "Conversational agent with thread-based memory for context awareness",
    type: "agent",
    url: "https://raw.githubusercontent.com/microsoft/agent-framework/main/python/samples/getting_started/agents/foundry/foundry_with_thread.py",
    tags: ["foundry", "memory", "thread"],
    author: "Microsoft",
    difficulty: "beginner",
    features: ["Thread memory", "Context tracking", "Persistent conversation"],
    requiredEnvVars: [
      {
        name: "AZURE_OPENAI_ENDPOINT",
        description: "Azure OpenAI service endpoint URL",
        required: true,
        example: "https://your-resource.openai.azure.com/",
      },
      {
        name: "AZURE_OPENAI_API_KEY",
        description: "API key for Azure OpenAI service",
        required: true,
      },
    ],
  },

  {
    id: "azure-chat-basic",
    name: "Azure Chat Agent",
    description: "Basic chat agent using Azure OpenAI Chat Completions API",
    type: "agent",
    url: "https://raw.githubusercontent.com/microsoft/agent-framework/main/python/samples/getting_started/agents/azure_chat_client/azure_chat_client_basic.py",
    tags: ["azure", "chat", "basic"],
    author: "Microsoft",
    difficulty: "beginner",
    features: ["Chat completions", "Azure integration", "Basic responses"],
    requiredEnvVars: [
      {
        name: "AZURE_OPENAI_ENDPOINT",
        description: "Azure OpenAI service endpoint URL",
        required: true,
        example: "https://your-resource.openai.azure.com/",
      },
      {
        name: "AZURE_OPENAI_API_KEY",
        description: "API key for Azure OpenAI service",
        required: true,
      },
    ],
  },

  // Intermediate Agents
  {
    id: "foundry-with-tools",
    name: "Tool-Enabled Agent",
    description:
      "Agent with function calling capabilities for enhanced interactions",
    type: "agent",
    url: "https://raw.githubusercontent.com/microsoft/agent-framework/main/python/samples/getting_started/agents/foundry/foundry_with_function_tools.py",
    tags: ["foundry", "tools", "functions"],
    author: "Microsoft",
    difficulty: "intermediate",
    features: ["Function calling", "Tool integration", "Enhanced capabilities"],
    requiredEnvVars: [
      {
        name: "AZURE_OPENAI_ENDPOINT",
        description: "Azure OpenAI service endpoint URL",
        required: true,
        example: "https://your-resource.openai.azure.com/",
      },
      {
        name: "AZURE_OPENAI_API_KEY",
        description: "API key for Azure OpenAI service",
        required: true,
      },
    ],
  },

  {
    id: "foundry-multiple-tools",
    name: "Multi-Tool Agent",
    description:
      "Advanced agent with multiple tools for complex task execution",
    type: "agent",
    url: "https://raw.githubusercontent.com/microsoft/agent-framework/main/python/samples/getting_started/agents/foundry/foundry_with_multiple_tools.py",
    tags: ["foundry", "multi-tool", "advanced"],
    author: "Microsoft",
    difficulty: "intermediate",
    features: ["Multiple tools", "Complex reasoning", "Task orchestration"],
    requiredEnvVars: [
      {
        name: "AZURE_OPENAI_ENDPOINT",
        description: "Azure OpenAI service endpoint URL",
        required: true,
        example: "https://your-resource.openai.azure.com/",
      },
      {
        name: "AZURE_OPENAI_API_KEY",
        description: "API key for Azure OpenAI service",
        required: true,
      },
    ],
  },

  {
    id: "azure-with-code-interpreter",
    name: "Code Interpreter Agent",
    description:
      "Agent with code execution capabilities for data analysis and computation",
    type: "agent",
    url: "https://raw.githubusercontent.com/microsoft/agent-framework/main/python/samples/getting_started/agents/azure_chat_client/azure_chat_client_with_code_interpreter.py",
    tags: ["azure", "code", "interpreter"],
    author: "Microsoft",
    difficulty: "intermediate",
    features: ["Code execution", "Data analysis", "Python runtime"],
    requiredEnvVars: [
      {
        name: "AZURE_OPENAI_ENDPOINT",
        description: "Azure OpenAI service endpoint URL",
        required: true,
        example: "https://your-resource.openai.azure.com/",
      },
      {
        name: "AZURE_OPENAI_API_KEY",
        description: "API key for Azure OpenAI service",
        required: true,
      },
    ],
  },

  // Beginner Workflows
  {
    id: "sequential-agents",
    name: "Sequential Agent Workflow",
    description: "Simple workflow that runs multiple agents in sequence",
    type: "workflow",
    url: "https://raw.githubusercontent.com/microsoft/agent-framework/main/python/samples/getting_started/workflow/orchestration/sequential_agents.py",
    tags: ["workflow", "sequential", "orchestration"],
    author: "Microsoft",
    difficulty: "beginner",
    features: [
      "Sequential execution",
      "Agent chaining",
      "Simple orchestration",
    ],
    requiredEnvVars: [
      {
        name: "AZURE_OPENAI_ENDPOINT",
        description: "Azure OpenAI service endpoint URL",
        required: true,
        example: "https://your-resource.openai.azure.com/",
      },
      {
        name: "AZURE_OPENAI_API_KEY",
        description: "API key for Azure OpenAI service",
        required: true,
      },
    ],
  },

  {
    id: "concurrent-agents",
    name: "Parallel Agent Workflow",
    description:
      "Execute multiple agents concurrently and aggregate their results",
    type: "workflow",
    url: "https://raw.githubusercontent.com/microsoft/agent-framework/main/python/samples/getting_started/workflow/orchestration/concurrent_agents.py",
    tags: ["workflow", "parallel", "concurrent"],
    author: "Microsoft",
    difficulty: "intermediate",
    features: [
      "Parallel execution",
      "Result aggregation",
      "Concurrency control",
    ],
    requiredEnvVars: [
      {
        name: "AZURE_OPENAI_ENDPOINT",
        description: "Azure OpenAI service endpoint URL",
        required: true,
        example: "https://your-resource.openai.azure.com/",
      },
      {
        name: "AZURE_OPENAI_API_KEY",
        description: "API key for Azure OpenAI service",
        required: true,
      },
    ],
  },

  // Advanced Workflows
  {
    id: "human-in-loop",
    name: "Human-in-the-Loop Workflow",
    description:
      "Interactive workflow that requires human input and approval at key steps",
    type: "workflow",
    url: "https://raw.githubusercontent.com/microsoft/agent-framework/main/python/samples/getting_started/workflow/human-in-the-loop/guessing_game_with_human_input.py",
    tags: ["workflow", "human", "interactive"],
    author: "Microsoft",
    difficulty: "advanced",
    features: ["Human interaction", "Approval gates", "Interactive flow"],
    requiredEnvVars: [
      {
        name: "AZURE_OPENAI_ENDPOINT",
        description: "Azure OpenAI service endpoint URL",
        required: true,
        example: "https://your-resource.openai.azure.com/",
      },
      {
        name: "AZURE_OPENAI_API_KEY",
        description: "API key for Azure OpenAI service",
        required: true,
      },
    ],
  },

  {
    id: "fan-out-fan-in",
    name: "Fan-out Fan-in Workflow",
    description:
      "Complex workflow pattern with parallel execution and result consolidation",
    type: "workflow",
    url: "https://raw.githubusercontent.com/microsoft/agent-framework/main/python/samples/getting_started/workflow/parallelism/fan_out_fan_in_edges.py",
    tags: ["workflow", "fan-out", "fan-in", "parallel"],
    author: "Microsoft",
    difficulty: "advanced",
    features: ["Fan-out pattern", "Parallel branches", "Result consolidation"],
    requiredEnvVars: [
      {
        name: "AZURE_OPENAI_ENDPOINT",
        description: "Azure OpenAI service endpoint URL",
        required: true,
        example: "https://your-resource.openai.azure.com/",
      },
      {
        name: "AZURE_OPENAI_API_KEY",
        description: "API key for Azure OpenAI service",
        required: true,
      },
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
