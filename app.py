import json
import streamlit as st
import asyncio
import os
import sys
import logging
from dotenv import load_dotenv
from openai import OpenAI

from mcp.client.sse import sse_client
from mcp import ClientSession

# Logging configuration
logging.basicConfig(
    filename="app_debug.log",
    level=logging.DEBUG,
    format='%(asctime)s - [APP] - %(levelname)s - %(message)s',
    encoding='utf-8'
)

load_dotenv()

# Read environment variables from the .env file to connect with LM Studio
API_KEY = os.getenv("API_KEY")
BASE_URL = os.getenv("LM_STUDIO_URL")
CRITICAL_TOOLS = {
    "git_commit",
    "git_push",
    "git_pull",
    "git_undo_last_commit",
    "write_file"
}

# Initialize OpenAI client configured for LM Studio
client = OpenAI(
    base_url=BASE_URL,
    api_key=API_KEY,
    timeout=60.0
)

def convert_tools(mcp_tools):
    """Converts tool in MCP format to format required by OpenAI API"""
    return[{
        "type": "function",
        "function":{
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.inputSchema
        }
    } for tool in mcp_tools]

async def ask_agent(user_input: str, messages_history: list):
    """Main function handling the agent's logic"""
    if messages_history is None:
        messages_history = []

    if user_input:
        logging.info(f"\n\nNew user request: {user_input}")
        messages_history.append({"role": "user", "content": user_input})
    else:
        logging.info("Resuming agent loop after human intervention.")

    server_url = "http://127.0.0.1:8000/sse"


    system_prompt = f"""
    You are an autonomous, Action-First AI assistant. Your primary goal is to fully resolve the user's request end-to-end using the tools available to you.

    CRITICAL RULES OF OPERATION:
    1. NEVER ASK FOR PERMISSION: Do not ask the user questions like "Should I check this?", "Would you like me to proceed?", or "Tell me the next step." If a step is logically required to fulfill the request, execute the appropriate tool immediately.
    2. ZERO LAZINESS: Do not instruct the user on how to perform a task if you have a tool capable of doing it. You must take the initiative to complete the work yourself.
    3. CHAIN YOUR ACTIONS: You operate in a continuous loop. You can call a tool, observe its output, and immediately call another tool based on those results until the task is done.
    4. NO HALLUCINATIONS: Never assume, guess, or make up facts, states, or data. If you lack information, use a tool to fetch it. 
    5. FINAL ANSWER: Only provide a final, conversational text response to the user when the task is 100% complete, or you have hit a definitive, unresolvable dead end. Do not narrate your intermediate steps to the user unless explicitly asked.

    ALWAYS OBSERVE BEFORE ACTING: If you need to choose, select, or modify something and you don't have the current list of items, your FIRST step MUST be to use a tool to list/observe the environment. NEVER guess names of files or directories.
    
    """
    try:
        # Start MCP client communicationg with server
        async with sse_client(server_url) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                logging.info("MCP session initialized.")

                # Fetch list of tools from MCP server and convert to OpenAI schema
                tools_response = await session.list_tools()
                openai_tools = convert_tools(tools_response.tools)

                # Agent loop iteration limit
                max_iterations = 5

                # Main agent loop
                for iteration in range(max_iterations):
                    logging.info(f"Agent loop - iteration: {iteration+1}")
                    system_prompt_msg = [{"role": "system", "content": system_prompt}] + messages_history

                    with st.spinner("LLM: Awaiting inference..."):
                        try:
                            # Request to the LLM with full history and list of available tools
                            response = client.chat.completions.create(
                                model="local-model",
                                messages=system_prompt_msg,
                                tools=openai_tools,
                                temperature=0.2
                            )
                        except Exception as e:
                            error_msg = f"API Connection Error: Cannot connect to LLM, check LM Studio. ({str(e)})"
                            logging.exception("Error connecting with LLM API.")
                            st.error(error_msg)
                            messages_history.append({"role": "assistant", "content": error_msg})
                            return

                    msg = response.choices[0].message

                    # Check if model decided to use a tool
                    if msg.tool_calls:
                        logging.info(f"Model decided to use {len(msg.tool_calls)} tool(s).")
                        messages_history.append(msg.model_dump())

                        for tool_call in msg.tool_calls:
                            tool_name = tool_call.function.name
                            tool_args_str = tool_call.function.arguments
                            logging.info(f"Calling tool: {tool_name} with arguments: {tool_args_str}")
                            try:
                                tool_args = json.loads(tool_args_str)
                            except Exception as e:
                                tool_args = {}
                                logging.error(f"JSON decode error: {e}")

                            hitl_active = st.session_state.get("hitl_enabled", True)
                            if hitl_active and (tool_name in CRITICAL_TOOLS):
                                st.session_state.pending_action = {
                                    "tool_call_id": tool_call.id,
                                    "name": tool_name,
                                    "args": tool_args
                                }
                                logging.info(f"Action {tool_name} paused for user approval.")
                                return

                            with st.status(f"Running tool: {tool_name}", expanded=True) as status:
                                st.write(f"Arguments: `{tool_args_str}`")

                                try:
                                    # Parse arguments generated by LLM and send to MCP server
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

                            # Save tool's result to the history so model sees it in next loop iteration
                            messages_history.append({
                                "tool_call_id": tool_call.id,
                                "role": "tool",
                                "name": tool_call.function.name,
                                "content": result_text
                            })
                        # Return to the beggining of the 'for' loop, the LLM analyzes the history again with the tool's result
                        continue

                    # If model didn't call a tool, returns the final text response
                    else:
                        logging.info("Model returned a text response. Ending loop.")
                        messages_history.append({"role": "assistant", "content": msg.content})
                        st.markdown(msg.content)
                        return
                    
                # Message when the loop hits the iteration limit
                timeout_msg = "Task required too many steps to complete."
                logging.warning("Maximum agent iterations exceeded.")
                messages_history.append({"role": "assistant", "content": timeout_msg})
                st.warning(timeout_msg)
    except Exception as e:
        error_msg = f"MCP Server Error: Could not connect with mcp_server.py. ({str(e)})"
        logging.exception("Error initializing MCP session.")
        st.error(error_msg)
        messages_history.append({"role": "assistant", "content": error_msg})


async def handle_pending_action(approved: bool):
    """Executes or rejects the action held in pending_action and resumes the agent loop."""
    action = st.session_state.pending_action
    if not action:
        return

    server_url = "http://127.0.0.1:8000/sse"

    if approved:
        try:
            async with sse_client(server_url) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(action["name"], action["args"])
                    result_text = result.content[0].text
        except Exception as e:
            result_text = f"Tool Execution Error: {str(e)}"
    else:
        result_text = "Operation CANCELLED by the user. Do not attempt this exact action again; propose an alternative or ask the user."

    st.session_state.history.append({
        "tool_call_id": action["tool_call_id"],
        "role": "tool",
        "name": action["name"],
        "content": result_text
    })

    st.session_state.pending_action = None

    await ask_agent(None, st.session_state.history)


# Streamlit UI configuration
st.set_page_config(page_title="LM Studio MCP App")
st.title("LM Studio MCP App")

# Sidebar with user tools (clear chat/logs)
with st.sidebar:
    st.header("Settings")

    st.toggle(
        "Wymagaj potwierdzeń (HITL)",
        value=True,
        key="hitl_enabled",
        help="Gdy włączone, agent wymaga akceptacji przed wykonaniem operacji modyfikujących (zapis plików, commity, push).",
        disabled=(st.session_state.get("pending_action") is not None)
    )

    if not st.session_state.get("hitl_enabled", True):
        st.warning("Tryb autonomiczny: Agent wykonuje wszystkie operacje bez pytania o zgodę.")

    st.divider()

    if st.button("Clear chat"):
        st.session_state.history = []
        st.rerun()

    if st.button("Clear logs"):
        log_files=["app_debug.log", "mcp_server_debug.log"]

        for file_path in log_files:
            if os.path.exists(file_path):
                try:
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.truncate(0)
                except Exception as e:
                    st.error(f"Couldn't clear {file_path}: {e}")
        st.success("Logs cleared.")





# Initialize conversation history in Streamlit session
if "history" not in st.session_state:
    st.session_state.history = []

if "pending_action" not in st.session_state:
    st.session_state.pending_action = None

# Render message history in the UI
for msg in st.session_state.history:
    role = msg.get("role")

    if role == "user":
        with st.chat_message("user"):
            st.markdown(msg.get("content", ""))

    elif role=="assistant":
        with st.chat_message("assistant"):

            # Replay tool usage information from history
            if msg.get("tool_calls"):
                for tool in msg["tool_calls"]:
                    with st.status(f"{tool['function']['name']}", state="complete"):
                        st.code(tool['function'].get("arguments", ""))
            
            if msg.get("content"):
                st.markdown(msg["content"])

    elif role == "tool":
        with st.expander(f"Tool: {msg['name']}"):
            st.code(msg.get("content", ""))



# Main chat input receiving prompt from user
if st.session_state.pending_action:
    action = st.session_state.pending_action
    
    st.markdown("---")
    with st.container(border=True):
        st.error(f"**Wymagana autoryzacja operacji:** `{action['name']}`")
        st.write("Sprawdź parametry przed zatwierdzeniem:")

        if action["name"] == "git_commit":
            st.info(f"**Wiadomość commita:** {action['args'].get('message')}")
            st.caption(f"Pliki: `{action['args'].get('files_to_add', '.')}` | Ścieżka: `{action['args'].get('repo_path', '.')}`")
        elif action["name"] == "write_file":
            st.info(f"**Plik:** `{action['args'].get('file_path')}`")
            st.code(action['args'].get('content', ''), language="python")
        else:
            st.json(action["args"])

        col1, col2 = st.columns([1, 4])
        with col1:
            if st.button("Zatwierdź i wykonaj", type="primary", use_container_width=True):
                with st.spinner("Wykonywanie operacji..."):
                    asyncio.run(handle_pending_action(approved=True))
                st.rerun()
        with col2:
            if st.button("Odrzuć operację", use_container_width=True):
                with st.spinner("Odrzucanie operacji..."):
                    asyncio.run(handle_pending_action(approved=False))
                st.rerun()


# Block input while waiting for user decision
is_waiting_for_approval = st.session_state.pending_action is not None
prompt_placeholder = "Wymagana decyzja powyżej..." if is_waiting_for_approval else "Wpisz polecenie dla asystenta..."

prompt = st.chat_input(prompt_placeholder, disabled=is_waiting_for_approval)

if prompt:
    with st.chat_message("user"):
        st.markdown(prompt)
    
    with st.chat_message("assistant"):
        with st.spinner("Executing task workflow..."):
            asyncio.run(ask_agent(prompt, st.session_state.history))

    st.rerun()