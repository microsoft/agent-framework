import { ChatKit, useChatKit } from "@openai/chatkit-react";

const CHATKIT_API_URL = "/chatkit";
const CHATKIT_API_DOMAIN_KEY =
  import.meta.env.VITE_CHATKIT_API_DOMAIN_KEY ?? "domain_pk_localhost_dev";

export default function App() {
  const chatkit = useChatKit({
    api: {
      url: CHATKIT_API_URL,
      domainKey: CHATKIT_API_DOMAIN_KEY,
      uploadStrategy: { type: "two_phase" },
    },
    startScreen: {
      greeting: "Hello! I'm your weather and image analysis assistant. Ask me about the weather in any location or upload images for me to analyze.",
      prompts: [
        { label: "Weather in New York", prompt: "What's the weather in New York?" },
        { label: "Select City to Get Weather", prompt: "Show me the city selector for weather" },
        { label: "Current Time", prompt: "What time is it?" },
        { label: "Analyze an Image", prompt: "I'll upload an image for you to analyze" },
      ],
    },
    composer: {
      placeholder: "Ask about weather or upload an image...",
      attachments: {
        enabled: true,
        accept: { "image/*": [".png", ".jpg", ".jpeg", ".gif", ".webp"] },
      },
    },
  });

  return <ChatKit control={chatkit.control} style={{ height: "100%" }} />;
}
