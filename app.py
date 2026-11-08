import json
import logging
import os
import urllib.parse

import requests
import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI

from mcp_client import MCPClient
from workspace import WorkspaceManager

# Logging configuration
logging.basicConfig(
    filename="app_debug.log",
    level=logging.DEBUG,
    format="%(asctime)s - [APP] - %(levelname)s - %(message)s",
    encoding="utf-8",
)

logger = logging.getLogger(__name__)

load_dotenv()

# Read environment variables from the .env file to connect with LM Studio
API_KEY = os.getenv("API_KEY")
BASE_URL = os.getenv("LM_STUDIO_URL")
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://127.0.0.1:8000/sse")


# Initialize OpenAI client configured for LM Studio
client = OpenAI(base_url=BASE_URL, api_key=API_KEY, timeout=200.0)


@st.cache_resource
def get_mcp_client() -> MCPClient:
    """Creates and retains a single MCP client throughout the Streamlit app lifecycle."""
    return MCPClient(MCP_SERVER_URL)


mcp_client = get_mcp_client()


def convert_tools(mcp_tools):
    """Converts tool in MCP format to format required by OpenAI API"""
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.inputSchema,
            },
        }
        for tool in mcp_tools
    ]


OPENAI_TOOLS = convert_tools(mcp_client.tools)


def ask_agent(user_input: str, messages_history: list):
    """Main function handling the agent's logic"""
    if messages_history is None:
        messages_history = []

    if user_input:
        logger.info(f"\n\nNew user request: {user_input}")
        messages_history.append({"role": "user", "content": user_input})
    else:
        logger.info("Resuming agent loop after human intervention.")

    # '/no_think' at the end of system prompt is used by Qwen models, it disables their reasoning resulting in faster answers and less token usage
    system_prompt = """
    You are a developer assistant connected to a local workspace via MCP tools. 
    Follow these instructions exactly:

    - Tools: Only use the tools explicitly provided to you. Never invent tool names. Use exactly one tool per turn.
    - Action: Don't ask for permission to run a tool or modify a file. Just do it. Assume tools automatically create missing parent directories.
    - Errors: If a tool fails, read the error carefully. You can try one alternative approach. If you are still stuck, stop immediately and tell the user. Never retry the exact same failing command.
    - File paths: Always use full target paths including the file extension (e.g., 'src/components/button.js'). Do not scan or inspect directories if the user already gave you the exact path.
    - Git: Always check status or diff before committing. Write concise Conventional Commits (e.g., 'feat: add login flow').
    - Communication: Do not narrate your step-by-step process. Stay silent while executing tools. Only write a text response when the entire task is finished, or if you hit an unresolvable error.
    /no_think
    """

    # Agent loop iteration limit
    max_iterations = 10

    # Main agent loop
    for iteration in range(max_iterations):
        logger.info(f"Agent loop - iteration: {iteration + 1}")
        system_prompt_msg = [
            {"role": "system", "content": system_prompt}
        ] + messages_history

        with st.spinner("LLM: Awaiting inference..."):
            try:
                # Request to the LLM with full history and list of available tools
                response = client.chat.completions.create(
                    model="local-model",
                    messages=system_prompt_msg,
                    tools=OPENAI_TOOLS,
                    temperature=0.2,
                    parallel_tool_calls=False,
                )
                if response.usage:
                    st.session_state.last_prompt_tokens = response.usage.prompt_tokens

            except Exception as e:
                error_msg = f"API Connection Error: Cannot connect to LLM, check LM Studio. ({e})"
                logger.exception("Error connecting with LLM API.")
                st.error(error_msg)
                messages_history.append({"role": "assistant", "content": error_msg})
                return

        msg = response.choices[0].message

        # Check if model decided to use a tool
        if msg.tool_calls:
            logger.info(f"Model decided to use {len(msg.tool_calls)} tool(s).")

            tool_call = msg.tool_calls[0]
            tool_name = tool_call.function.name
            tool_args_str = tool_call.function.arguments

            sanitized_assistant_msg = {
                "role": "assistant",
                "content": msg.content,
                "tool_calls": [tool_call.model_dump()],
            }

            logger.info(f"Calling tool: {tool_name} with arguments: {tool_args_str}")
            try:
                tool_args = json.loads(tool_args_str)
            except Exception as e:
                tool_args = {}
                logger.error(f"JSON decode error: {e}")

            hitl_active = st.session_state.get("hitl_enabled", True)
            if hitl_active and is_tool_critical(tool_name):
                st.session_state.pending_action = {
                    "tool_call_id": tool_call.id,
                    "name": tool_name,
                    "args": tool_args,
                    "raw_msg": sanitized_assistant_msg,
                }
                logger.info(f"Action {tool_name} paused for user approval.")
                return

            messages_history.append(sanitized_assistant_msg)

            with st.status(f"Running tool: {tool_name}", expanded=True) as status:
                st.write(f"Arguments: `{tool_args_str}`")

                try:
                    result_text, is_error = mcp_client.call_tool(tool_name, tool_args)
                    if is_error:
                        logger.warning(
                            f"Server reported error for {tool_name}: {result_text}"
                        )
                        status.update(label=f"Failed: {tool_name}", state="error")
                        st.error(result_text)
                        tool_content_for_llm = f"[TOOL ERROR]: {result_text}"
                    else:
                        logger.debug(f"Server result for {tool_name}: {result_text}")
                        status.update(label=f"Completed: {tool_name}", state="complete")
                        st.success("Completed")
                        st.code(result_text)
                        tool_content_for_llm = result_text
                except Exception as e:
                    tool_content_for_llm = f"App error using tool: {e}"
                    logger.exception(
                        f"App error during communication with tool {tool_name}"
                    )
                    status.update(label=f"Execution error: {tool_name}", state="error")
                    st.error(tool_content_for_llm)

            # Save tool's result to the history so model sees it in next loop iteration
            messages_history.append(
                {
                    "tool_call_id": tool_call.id,
                    "role": "tool",
                    "name": tool_name,
                    "content": tool_content_for_llm,
                }
            )
            continue

        # If model didn't call a tool, returns the final text response
        else:
            logger.info("Model returned a text response. Ending loop.")
            messages_history.append({"role": "assistant", "content": msg.content})
            st.markdown(msg.content)
            return

    # Message when the loop hits the iteration limit
    timeout_msg = "Task required too many steps to complete."
    logger.warning("Maximum agent iterations exceeded.")
    messages_history.append({"role": "assistant", "content": timeout_msg})
    st.warning(timeout_msg)


def handle_pending_action(approved: bool):
    """Executes or rejects the action held in pending_action and resumes the agent loop."""
    action = st.session_state.pending_action
    if not action:
        return

    st.session_state.history.append(action["raw_msg"])

    if approved:
        try:
            result_text, is_error = mcp_client.call_tool(action["name"], action["args"])
            if is_error:
                result_text = f"[TOOL ERROR]: {result_text}"
        except Exception as e:
            result_text = f"[TOOL ERROR]: {e}"
    else:
        result_text = "Operation cancelled by the user. Do not attempt this exact action again; propose an alternative or ask the user."

    st.session_state.history.append(
        {
            "tool_call_id": action["tool_call_id"],
            "role": "tool",
            "name": action["name"],
            "content": result_text,
        }
    )

    st.session_state.pending_action = None
    st.session_state.resume_agent = True


def is_tool_critical(tool_name: str) -> bool:
    for tool in mcp_client.tools:
        if tool.name == tool_name and tool.annotations:
            if tool.annotations.readOnlyHint is True:
                return False
            return True
    return True


def get_lmstudio_model_info():
    """Gets informations about currently loaded model from LM Studio."""
    base_uri = urllib.parse.urlparse(BASE_URL)
    api_url = f"{base_uri.scheme}://{base_uri.netloc}/api/v0/models"

    try:
        response = requests.get(api_url, timeout=2.0)
        if response.status_code == 200:
            data = response.json()
            if data.get("data") and len(data["data"]) > 0:
                return data["data"][0]
        return None
    except requests.RequestException:
        logger.warning("Couldn't fetch info about model from /api/v0/models")
        return None


st.set_page_config(page_title="LM Studio MCP App")
st.title("LM Studio MCP App")

with st.expander("Stats", expanded=False):
    model_info = get_lmstudio_model_info()

    if model_info:
        model_name = model_info.get("id", "Unknonwn model")
        quantization = model_info.get("quantization", "N/A")
        max_context = model_info.get("loaded_context_length", 0)

        col1, col2, col3 = st.columns(3)

        with col1:
            st.markdown("Model name:")
            st.markdown(f"{model_name}")
        with col2:
            st.markdown("Quantization:")
            st.markdown(f"{quantization}")
        with col3:
            current_tokens = st.session_state.get("last_prompt_tokens", 0)
            st.write("Context used: ")
            if current_tokens > 0:
                if max_context > 0:
                    progress_val = min(current_tokens / max_context, 1.0)
                    st.progress(progress_val, text=f"{current_tokens} / {max_context}")
                else:
                    st.write(f"{current_tokens} t")
            else:
                st.write("Waiting for prompt")
    else:
        st.error("Model not detected")

# Sidebar with user tools (clear chat/logs)
with st.sidebar:
    st.header("Settings")

    current_ws = str(WorkspaceManager.get_workspace())
    target_ws = st.text_input("Workspace folder:", value=current_ws)

    if st.button("Apply workspace", use_container_width=True):
        try:
            applied = WorkspaceManager.set_workspace(target_ws)
            st.session_state.pending_action = None

            if st.session_state.get("history"):
                st.session_state.history.append(
                    {
                        "role": "user",
                        "content": f"[WORKSPACE CHANGED]: The working directory is now set to '{applied}'. "
                        "All tool operations and file paths will be relative to this folder.",
                    }
                )
            st.success(f"Set to: {applied.name}")
            st.rerun()
        except Exception as e:
            st.error(f"Error: {e}")

    st.caption("Currently active path:")
    st.caption(current_ws)

    st.divider()
    st.header("MCP Prompts")
    st.caption("Click to run:")

    is_busy = (
        st.session_state.get("pending_action") is not None
    ) or st.session_state.get("resume_agent", False)

    for p in mcp_client.prompts:
        button_title = f"{p.name.replace('_', ' ').capitalize()}"

        if st.button(
            button_title, help=p.description, use_container_width=True, disabled=is_busy
        ):
            try:
                prompt_body = mcp_client.get_prompt(p.name)
                st.session_state.pending_prompt_text = prompt_body
                st.rerun()
            except Exception as e:
                st.error(f"Error loading prompt: {e}")

    st.divider()

    st.toggle(
        "Require confirmations",
        value=True,
        key="hitl_enabled",
        help="When enabled, agent requires approval before executing potentially dangerous tools.",
        disabled=(st.session_state.get("pending_action") is not None),
    )

    if not st.session_state.get("hitl_enabled", True):
        st.warning("Agent executes all tools without asking for permission.")

    st.divider()
    with st.expander("Available tools", expanded=False):
        if mcp_client.tools:
            for tool in mcp_client.tools:
                with st.expander(f"{tool.name}"):
                    st.write(tool.description)
        else:
            st.warning("No tools loaded.")

    st.divider()

    if st.button("Clear chat"):
        st.session_state.history = []
        st.rerun()

    if st.button("Clear logs"):
        log_files = ["app_debug.log", "mcp_server_debug.log"]

        for file_path in log_files:
            if os.path.exists(file_path):
                try:
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.truncate(0)
                except Exception as e:
                    st.error(f"Couldn't clear {file_path}: {e}")
        st.success("Logs cleared.")

    if st.button("Reconnect MCP Server"):
        mcp_client.close()
        st.cache_resource.clear()
        st.session_state.history = []
        st.rerun()


# Initialize conversation history in Streamlit session
if "history" not in st.session_state:
    st.session_state.history = []

if "pending_action" not in st.session_state:
    st.session_state.pending_action = None

if "resume_agent" not in st.session_state:
    st.session_state.resume_agent = False

if "pending_prompt_text" not in st.session_state:
    st.session_state.pending_prompt_text = None

tool_results = {
    msg["tool_call_id"]: msg.get("content", "")
    for msg in st.session_state.history
    if msg.get("role") == "tool" and "tool_call_id" in msg
}

# Render message history in the UI
for msg in st.session_state.history:
    role = msg.get("role")

    if role == "user":
        with st.chat_message("user"):
            st.markdown(msg.get("content", ""))

    elif role == "assistant":
        with st.chat_message("assistant"):
            if msg.get("tool_calls"):
                for tool in msg["tool_calls"]:
                    call_id = tool.get("id")
                    tool_name = tool["function"]["name"]
                    result_content = tool_results.get(call_id, "")
                    is_failed = result_content.startswith(("[TOOL ERROR]", "App error"))

                    status_label = (
                        f"Failed: {tool_name}"
                        if is_failed
                        else f"Completed: {tool_name}"
                    )
                    with st.status(
                        status_label,
                        state="error" if is_failed else "complete",
                        expanded=False,
                    ):
                        st.write("Arguments:")
                        st.code(tool["function"].get("arguments", ""))

            if msg.get("content"):
                st.markdown(msg["content"])

    elif role == "tool":
        content = msg.get("content", "")
        is_failed = content.startswith(("[TOOL ERROR]", "App error"))
        label = f"Tool output: {msg.get('name')}" + (" (Error)" if is_failed else "")

        with st.expander(label, expanded=is_failed):
            if is_failed:
                st.error(content)
            else:
                st.code(content)


# Main chat input receiving prompt from user
if st.session_state.pending_action:
    action = st.session_state.pending_action

    st.markdown("---")
    with st.container(border=True):
        st.error(f"**Autorization needed:** `{action['name']}`")
        st.write("Check parameters: ")

        if action["name"] == "git_commit":
            st.info(f"**Commit message:** {action['args'].get('message')}")
            st.caption(
                f"Files: `{action['args'].get('files_to_add', '.')}` | Path: `{action['args'].get('repo_path', '.')}`"
            )
        elif action["name"] == "write_file":
            st.info(f"**File:** `{action['args'].get('file_path')}`")
            st.code(action["args"].get("content", ""), language="python")
        else:
            st.json(action["args"])

        col1, col2 = st.columns([1, 4])
        with col1:
            if st.button("Approve", type="primary", use_container_width=True):
                handle_pending_action(approved=True)
                st.rerun()
        with col2:
            if st.button("Reject", use_container_width=True):
                handle_pending_action(approved=False)
                st.rerun()


# Block input while waiting for user decision
is_waiting_for_approval = st.session_state.pending_action is not None
prompt_placeholder = (
    "Decision required..."
    if is_waiting_for_approval
    else "Enter prompt for assistant..."
)


if st.session_state.resume_agent:
    st.session_state.resume_agent = False
    with st.chat_message("assistant"):
        ask_agent(None, st.session_state.history)
    st.rerun()

triggered_from_button = st.session_state.pending_prompt_text
if triggered_from_button:
    st.session_state.pending_prompt_text = None

prompt = st.chat_input(prompt_placeholder, disabled=is_waiting_for_approval)

user_message = triggered_from_button or prompt

if user_message:
    with st.chat_message("user"):
        st.markdown(user_message)

    with st.chat_message("assistant"):
        ask_agent(user_message, st.session_state.history)

    st.rerun()
