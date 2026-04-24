import json
import streamlit as st
import asyncio
import os
from dotenv import load_dotenv
from openai import OpenAI

from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp import ClientSession

load_dotenv()

API_KEY = os.getenv("API_KEY")
BASE_URL = os.getenv("LM_STUDIO_URL")

client = OpenAI(
    base_url=BASE_URL,
    api_key=API_KEY,
    timeout=60.0
)

def convert_tools(mcp_tools):
    return[{
        "type": "function",
        "function":{
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.inputSchema
        }
    } for tool in mcp_tools]

async def ask_agent(user_input: str, messages_history: list):
    server_params = StdioServerParameters(
        command="python",
        args=["mcp_server.py"]
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools_response = await session.list_tools()
            openai_tools = convert_tools(tools_response.tools)

            messages_history.append({"role": "user", "content": user_input})

            max_iterations = 5

            for iteration in range(max_iterations):

                with st.spinner("Analyzing..."):
                    response = client.chat.completions.create(
                        model="local-model",
                        messages=messages_history,
                        tools=openai_tools
                    )

                msg = response.choices[0].message

                if msg.tool_calls:
                    messages_history.append(msg.model_dump())

                    for tool_call in msg.tool_calls:
                        tool_name = tool_call.function.name
                        tool_args_str = tool_call.function.arguments

                        with st.status(f"Running tool: {tool_name}", expanded=True) as status:
                            st.write(f"Arguments: `{tool_args_str}`")

                            try:
                                tool_args = json.loads(tool_args_str)
                                result = await session.call_tool(
                                    tool_name,
                                    tool_args
                                )
                                result_text = result.content[0].text
                                st.success("Completed")
                                st.code(result_text)
                            except Exception as e:
                                result_text=f"Error using tool: {str(e)}"
                                st.error(result_text)

                            status.update(state="complete")

                        messages_history.append({
                            "tool_call_id": tool_call.id,
                            "role": "tool",
                            "name": tool_call.function.name,
                            "content": result_text
                        })
                    continue

                else:
                    messages_history.append({"role": "assistant", "content": msg.content})
                    st.markdown(msg.content)
                    return
                
            timeout_msg = "Task required too many steps to complete."
            messages_history.append({"role": "assistant", "content": timeout_msg})
            st.warning(timeout_msg)
                


st.set_page_config(page_title="LM Studio MCP App")
st.title("LM Studio MCP App")

with st.sidebar:
    st.header("Settings")

    if st.button("Clear chat"):
        st.session_state.history = []
        st.rerun()

if "history" not in st.session_state:
    st.session_state.history = []

for msg in st.session_state.history:
    role = msg.get("role")

    if role == "user":
        with st.chat_message("user"):
            st.markdown(msg.get("content", ""))

    elif role=="assistant":
        with st.chat_message("assistant"):

            if msg.get("tool_calls"):
                for tool in msg["tool_calls"]:
                    with st.status(f"{tool['function']['name']}", state="complete"):
                        st.code(tool['function'].get("arguments", ""))
            
            if msg.get("content"):
                st.markdown(msg["content"])

    elif role == "tool":
        with st.expander(f"Tool: {msg['name']}"):
            st.code(msg.get("content", ""))




prompt = st.chat_input("Hello world!")

if prompt:
    with st.chat_message("user"):
        st.markdown(prompt)
    
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            answer = asyncio.run(ask_agent(prompt, st.session_state.history))

    st.rerun()