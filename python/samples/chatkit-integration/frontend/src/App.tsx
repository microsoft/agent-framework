import { ChatKit, useChatKit } from "@openai/chatkit-react";

const CHATKIT_API_URL = "/chatkit";
const CHATKIT_API_DOMAIN_KEY =
  import.meta.env.VITE_CHATKIT_API_DOMAIN_KEY ?? "domain_pk_localhost_dev";

export default function App() {
  const chatkit = useChatKit({
    api: {
      url: CHATKIT_API_URL,
      domainKey: CHATKIT_API_DOMAIN_KEY,
    },
    startScreen: {
      greeting: "Hello! I'm your weather assistant. Ask me about the weather in any location.",
      prompts: [
        { label: "Weather in New York", prompt: "What's the weather in New York?" },
        { label: "Weather in London", prompt: "Tell me the weather in London" },
        { label: "Current Time", prompt: "What time is it?" },
      ],
    },
  });

  return <ChatKit control={chatkit.control} style={{ height: "100%" }} />;
}
