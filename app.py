import json
import streamlit as st
import asyncio
import os
import logging
from dotenv import load_dotenv
from openai import OpenAI

from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp import ClientSession

logging.basicConfig(
    filename="app_debug.log",
    level=logging.DEBUG,
    format='%(asctime)s - [APP] - %(levelname)s - %(message)s',
    encoding='utf-8'
)

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
    logging.info(f"\n\nNew user request: {user_input}")
    server_params = StdioServerParameters(
        command="python",
        args=["mcp_server.py"]
    )

    system_prompt = f"""
    You are an autonomous, Action-First AI assistant. Your primary goal is to fully resolve the user's request end-to-end using the tools available to you.

    CRITICAL RULES OF OPERATION:
    1. NEVER ASK FOR PERMISSION: Do not ask the user questions like "Should I check this?", "Would you like me to proceed?", or "Tell me the next step." If a step is logically required to fulfill the request, execute the appropriate tool immediately.
    2. ZERO LAZINESS: Do not instruct the user on how to perform a task if you have a tool capable of doing it. You must take the initiative to complete the work yourself.
    3. CHAIN YOUR ACTIONS: You operate in a continuous loop. You can call a tool, observe its output, and immediately call another tool based on those results until the task is done.
    4. NO HALLUCINATIONS: Never assume, guess, or make up facts, states, or data. If you lack information, use a tool to fetch it. 
    5. FINAL ANSWER: Only provide a final, conversational text response to the user when the task is 100% complete, or you have hit a definitive, unresolvable dead end. Do not narrate your intermediate steps to the user unless explicitly asked.

    ALWAYS OBSERVE BEFORE ACTING: If you need to choose, select, or modify something and you don't have the current list of items, your FIRST step MUST be to use a tool to list/observe the environment. NEVER guess names of files or directories.
    
    /no_think
    """

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            logging.info("MCP session initialized.")

            tools_response = await session.list_tools()
            openai_tools = convert_tools(tools_response.tools)

            messages_history.append({"role": "user", "content": user_input})

            max_iterations = 5

            for iteration in range(max_iterations):
                logging.info(f"Agent loop - iteration: {iteration+1}")
                system_prompt_msg = [{"role": "system", "content": system_prompt}] + messages_history

                with st.spinner("Analyzing..."):
                    response = client.chat.completions.create(
                        model="local-model",
                        messages=system_prompt_msg,
                        tools=openai_tools,
                        temperature=0.2
                    )

                msg = response.choices[0].message

                if msg.tool_calls:
                    logging.info(f"Model decided to use {len(msg.tool_calls)} tool(s).")
                    messages_history.append(msg.model_dump())

                    for tool_call in msg.tool_calls:
                        tool_name = tool_call.function.name
                        tool_args_str = tool_call.function.arguments
                        logging.info(f"Calling tool: {tool_name} with arguments: {tool_args_str}")

                        with st.status(f"Running tool: {tool_name}", expanded=True) as status:
                            st.write(f"Arguments: `{tool_args_str}`")

                            try:
                                tool_args = json.loads(tool_args_str)
                                result = await session.call_tool(
                                    tool_name,
                                    tool_args
                                )
                                result_text = result.content[0].text
                                logging.debug(f"Server result for {tool_name}: {result_text}")
                                st.success("Completed")
                                st.code(result_text)
                            except Exception as e:
                                result_text=f"Error using tool: {str(e)}"
                                logging.exception(f"App error during communication with tool {tool_name}")
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
                    logging.info("Model returned a text response. Ending loop.")
                    messages_history.append({"role": "assistant", "content": msg.content})
                    st.markdown(msg.content)
                    return
                
            timeout_msg = "Task required too many steps to complete."
            logging.warning("Maximum agent iterations exceeded.")
            messages_history.append({"role": "assistant", "content": timeout_msg})
            st.warning(timeout_msg)
                


st.set_page_config(page_title="LM Studio MCP App")
st.title("LM Studio MCP App")

with st.sidebar:
    st.header("Settings")

    if st.button("Clear chat"):
        st.session_state.history = []
        st.rerun()

    if st.button("Clear logs"):
        log_files=["app_debug.log", "mcp_server.log"]

        for file_path in log_files:
            if os.path.exists(file_path):
                try:
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.truncate(0)
                except Exception as e:
                    st.error(f"Couldn't clear {file_path}: {e}")
        st.success("Logs cleared.")

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