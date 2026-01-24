# Copyright (c) Microsoft. All rights reserved.

"""
Gradio Chat UI for testing Azure Functions streaming endpoints.

Usage:
    pip install gradio requests
    python gradio_chat.py
"""

import gradio as gr
import requests
import json


def chat_with_agent(message, endpoint, history):
    """Stream response from the agent or workflow endpoint."""
    if not message.strip():
        return history
    
    try:
        response = requests.post(
            endpoint,
            json={"message": message},
            stream=True,
            timeout=240
        )
        
        if response.status_code != 200:
            error_msg = f"Error {response.status_code}: {response.text}"
            history.append({"role": "user", "content": message})
            history.append({"role": "assistant", "content": error_msg})
            return history
        
        # Add user message and empty agent response
        history.append({"role": "user", "content": message})
        history.append({"role": "assistant", "content": ""})
        
        agent_response = ""
        for line in response.iter_lines():
            if line.startswith(b'data: '):
                try:
                    data = json.loads(line[6:])
                    if data.get('text'):
                        agent_response += data['text']
                        # Update the last message with accumulated response
                        history[-1]["content"] = agent_response
                        yield history
                except json.JSONDecodeError:
                    pass
        
        # Final update
        history[-1]["content"] = agent_response if agent_response else "No response received"
        yield history
        
    except requests.exceptions.Timeout:
        history.append({"role": "user", "content": message})
        history.append({"role": "assistant", "content": "⚠️ Request timed out (>240s)"})
        yield history
    except Exception as e:
        history.append({"role": "user", "content": message})
        history.append({"role": "assistant", "content": f"❌ Error: {str(e)}"})
        yield history


# Create the Gradio interface
with gr.Blocks(title="Agent Chat UI") as demo:
    gr.Markdown(
        """
        # 🤖 Agent Framework Chat UI
        
        Test your Azure Functions streaming endpoints with a simple chat interface.
        Make sure your function app is running on `http://localhost:7071`
        """
    )
    
    with gr.Row():
        endpoint = gr.Radio(
            choices=[
                "http://localhost:7071/api/agent/stream",
                "http://localhost:7071/api/workflow/stream"
            ],
            value="http://localhost:7071/api/agent/stream",
            label="🎯 Select Endpoint",
            info="Choose between single agent or multi-agent workflow"
        )
    
    chatbot = gr.Chatbot(
        height=500,
        label="Chat",
        avatar_images=(None, "🤖")
    )
    
    with gr.Row():
        msg = gr.Textbox(
            placeholder="Type your message here... (e.g., 'What's the weather in Seattle?')",
            label="Message",
            scale=9
        )
        submit_btn = gr.Button("Send", scale=1, variant="primary")
    
    with gr.Row():
        clear_btn = gr.Button("🗑️ Clear Chat")
    
    gr.Markdown(
        """
        ### 💡 Try these examples:
        - "What's the weather in Seattle?"
        - "Tell me about the weather in Tokyo and Paris"
        - "Research the weather in London and write a short poem about it" (workflow)
        """
    )
    
    # Event handlers
    def submit_message(message, chat_history, endpoint_url):
        for updated_history in chat_with_agent(message, endpoint_url, chat_history):
            yield updated_history
    
    msg.submit(
        submit_message,
        [msg, chatbot, endpoint],
        chatbot
    ).then(
        lambda: "",
        None,
        msg
    )
    
    submit_btn.click(
        submit_message,
        [msg, chatbot, endpoint],
        chatbot
    ).then(
        lambda: "",
        None,
        msg
    )
    
    clear_btn.click(lambda: [], None, chatbot)


if __name__ == "__main__":
    print("\n🚀 Starting Gradio Chat UI...")
    print("📍 Make sure your Azure Function is running on http://localhost:7071")
    print("🌐 Opening browser...\n")
    
    demo.launch(
        server_name="127.0.0.1",
        server_port=7860,
        show_error=True,
        share=False,  # Set to True to create a public URL
        theme=gr.themes.Soft()
    )
