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

def conver_tools(mcp_tools):
    return[{
        "type": "function",
        "function":{
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.inputSchema
        }
    } for tool in mcp_tools]

async def ask_agent(user_input: str):
    server_params = StdioServerParameters(
        command="python",
        args=["mcp_server.py"]
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools_response = await session.list_tools()
            openai_tools = conver_tools(tools_response.tools)

            messages = [
                {"role": "user", "content": user_input}
            ]

            response = client.chat.completions.create(
                model="local-model",
                messages=messages,
                tools=openai_tools
            )

            msg = response.choices[0].message

            if msg.tool_calls:
                tool_call = msg.tool_calls[0]
                result = await session.call_tool(
                    tool_call.function.name,
                    {}
                )

                return result.content[0].text
            return msg.content
            


st.title("LM Studio MCP App")

if "history" not in st.session_state:
    st.session_state.history = []

for h in st.session_state.history:
    st.write(h)

prompt = st.chat_input("Hello world!")

if prompt:
    st.session_state.history.append(f"You: {prompt}")

    with st.spinner("Thinking..."):
        answer = asyncio.run(ask_agent(prompt))

    st.session_state.history.append(f"AI: {answer}")

    st.rerun()