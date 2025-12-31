# Copyright (c) Microsoft. All rights reserved.

"""
Streamlit Chat UI for testing Azure Functions streaming endpoints.

Features:
- Persistent sessions across page refreshes using URL query parameters
- Support for both single agent and multi-agent workflows
- Session management with conversation history

Usage:
    pip install streamlit requests
    streamlit run streamlit_chat.py
"""

import json
import uuid

import requests
import streamlit as st

# Configure page
st.set_page_config(page_title="Agent Framework Chat", page_icon="🤖", layout="centered")

# Get session ID from URL query parameters
query_params = st.query_params
url_session_id = query_params.get("session_id")

# Initialize session state with persistence
if "sessions" not in st.session_state:
    st.session_state.sessions = {}

if "current_session_id" not in st.session_state:
    # If there's a session ID in URL, use it
    if url_session_id:
        st.session_state.current_session_id = url_session_id
        if url_session_id not in st.session_state.sessions:
            st.session_state.sessions[url_session_id] = []
    else:
        st.session_state.current_session_id = None
        
if "messages" not in st.session_state:
    # Load messages for current session
    if st.session_state.current_session_id:
        st.session_state.messages = st.session_state.sessions.get(
            st.session_state.current_session_id, []
        )
    else:
        st.session_state.messages = []

# Sidebar configuration
with st.sidebar:
    st.title("⚙️ Configuration")
    
    # Endpoint selection
    endpoint = st.radio(
        "Select Endpoint",
        [
            "http://localhost:7071/api/agent/stream",
            "http://localhost:7071/api/workflow/stream",
        ],
        index=0,
        help="Choose between single agent or multi-agent workflow",
    )
    
    st.markdown("---")
    st.markdown("### 💬 Session Management")
    
    # Session selection/creation
    col1, col2 = st.columns(2)
    with col1:
        if st.button("➕ New Session", use_container_width=True):
            new_session_id = str(uuid.uuid4())[:8]
            st.session_state.sessions[new_session_id] = []
            st.session_state.current_session_id = new_session_id
            st.session_state.messages = []
            # Update URL to persist session across refresh
            st.query_params["session_id"] = new_session_id
            st.rerun()
    
    with col2:
        if st.button("🚫 No Session", use_container_width=True):
            st.session_state.current_session_id = None
            st.session_state.messages = []
            # Remove session from URL
            if "session_id" in st.query_params:
                del st.query_params["session_id"]
            st.rerun()
    
    # Display existing sessions
    if st.session_state.sessions:
        st.markdown("**Existing Sessions:**")
        for session_id in list(st.session_state.sessions.keys()):
            col_a, col_b = st.columns([3, 1])
            with col_a:
                if st.button(
                    f"{'🟢' if session_id == st.session_state.current_session_id else '⚪'} {session_id}",
                    key=f"session_{session_id}",
                    use_container_width=True
                ):
                    st.session_state.current_session_id = session_id
                    st.session_state.messages = st.session_state.sessions[session_id]
                    # Update URL to persist session across refresh
                    st.query_params["session_id"] = session_id
                    st.rerun()
            with col_b:
                if st.button("🗑️", key=f"delete_{session_id}"):
                    del st.session_state.sessions[session_id]
                    if st.session_state.current_session_id == session_id:
                        st.session_state.current_session_id = None
                        st.session_state.messages = []
                        # Remove session from URL
                        if "session_id" in st.query_params:
                            del st.query_params["session_id"]
                    st.rerun()
    
    st.markdown("---")
    st.markdown("### 💡 Try these examples:")
    st.markdown("- What's the weather in Seattle?")
    st.markdown("- Tell me about the weather in Tokyo and Paris")
    st.markdown("- Research the weather in London (workflow)")
    
    st.markdown("---")
    if st.button("🗑️ Clear Current Chat", use_container_width=True):
        st.session_state.messages = []
        if st.session_state.current_session_id:
            st.session_state.sessions[st.session_state.current_session_id] = []
        st.rerun()

# Main chat interface
st.title("🤖 Agent Framework Chat UI")
if st.session_state.current_session_id:
    st.caption(f"Session: {st.session_state.current_session_id}")
    st.caption("💡 This session persists across page refreshes (stored in Azure)")
else:
    st.caption("No session (stateless mode)")

# Display chat history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Chat input
if prompt := st.chat_input("Type your message here..."):
    # Add user message to history
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    # Save to session storage
    if st.session_state.current_session_id:
        st.session_state.sessions[st.session_state.current_session_id] = st.session_state.messages.copy()
    
    # Display user message
    with st.chat_message("user"):
        st.markdown(prompt)
    
    # Display assistant response with streaming
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        full_response = ""
        
        try:
            # Prepare request payload
            payload = {"message": prompt}
            if st.session_state.current_session_id:
                payload["session_id"] = st.session_state.current_session_id
            
            # Make streaming request to the endpoint
            response = requests.post(
                endpoint,
                json=payload,
                stream=True,
                timeout=240
            )
            
            if response.status_code == 200:
                # Process SSE stream
                for line in response.iter_lines():
                    if line.startswith(b'data: '):
                        try:
                            data = json.loads(line[6:])
                            if data.get('text'):
                                full_response += data['text']
                                message_placeholder.markdown(full_response + "▌")
                        except json.JSONDecodeError:
                            pass
                
                # Final update without cursor
                message_placeholder.markdown(full_response)
            else:
                error_msg = f"❌ Error {response.status_code}: {response.text}"
                full_response = error_msg
                message_placeholder.markdown(error_msg)
        
        except requests.exceptions.Timeout:
            error_msg = "⚠️ Request timed out (>240s)"
            full_response = error_msg
            message_placeholder.markdown(error_msg)
        except Exception as e:
            error_msg = f"❌ Error: {str(e)}"
            full_response = error_msg
            message_placeholder.markdown(error_msg)
        
        # Add assistant response to history
        st.session_state.messages.append({"role": "assistant", "content": full_response})
        
        # Save to session storage
        if st.session_state.current_session_id:
            st.session_state.sessions[st.session_state.current_session_id] = st.session_state.messages.copy()

# Footer
st.markdown("---")
st.caption("📍 Make sure your Azure Function is running on http://localhost:7071")
