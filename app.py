import json
import logging
import os

import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI

from mcp_client import PersistentMCPClient
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
client = OpenAI(base_url=BASE_URL, api_key=API_KEY, timeout=60.0)


@st.cache_resource
def get_mcp_client() -> PersistentMCPClient:
    """Creates and retains a single MCP client throughout the Streamlit app lifecycle."""
    return PersistentMCPClient(MCP_SERVER_URL)


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

    system_prompt = """
    You are an autonomous, Action-First AI assistant. Your primary goal is to fully resolve the user's request end-to-end using the tools available to you.

    CRITICAL RULES OF OPERATION:
    1. NEVER ASK FOR PERMISSION: Do not ask the user questions like "Should I check this?", "Would you like me to proceed?", or "Tell me the next step." If a step is logically required to fulfill the request, execute the appropriate tool immediately.
    2. ZERO LAZINESS: Do not instruct the user on how to perform a task if you have a tool capable of doing it. You must take the initiative to complete the work yourself.
    3. CHAIN YOUR ACTIONS: You operate in a continuous loop. You can call a tool, observe its output, and immediately call another tool based on those results until the task is done.
    4. NO HALLUCINATIONS: Never assume, guess, or make up facts, states, or data. If you lack information, use a tool to fetch it. 
    5. FINAL ANSWER: Only provide a final, conversational text response to the user when the task is 100% complete, or you have hit a definitive, unresolvable dead end. Do not narrate your intermediate steps to the user unless explicitly asked.
    6. STRICTLY ONE TOOL PER STEP: You can and must execute only ONE tool call at a time.
    7. HANDLING MULTI-ITEM REQUESTS: When a user asks to perform multiple actions (e.g. create multiple files, run several checks, or asks to do something "at once", "together", "in one approach"), this means you must execute them AUTONOMOUSLY STEP-BY-STEP in a loop. Never try to do them all in a single tool call, and NEVER stop until ALL requested items are completed.
    8. FORBIDDEN PREMATURE TEXT: Do NOT output conversational text until 100% of the requested items/actions are finished. If the user asked for 2 files and you have created only 1, calling a text response is an error—you MUST immediately invoke the next tool call for the remaining file.

    ALWAYS OBSERVE BEFORE ACTING: If you need to choose, select, or modify something and you don't have the current list of items, your FIRST step MUST be to use a tool to list/observe the environment. NEVER guess names of files or directories.
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
            result_text = f"Tool Execution Error: {e}"
    else:
        result_text = "Operation CANCELLED by the user. Do not attempt this exact action again; propose an alternative or ask the user."

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
        if tool.name == tool_name:
            ann = getattr(tool, "annotations", None)
            if not ann:
                return True

            if hasattr(ann, "model_dump"):
                data = ann.model_dump()
            elif isinstance(ann, dict):
                data = ann
            else:
                data = {
                    "readOnlyHint": getattr(
                        ann,
                        "readOnlyHint",
                        getattr(ann, "read_only_hint", None),
                    ),
                    "destructiveHint": getattr(
                        ann,
                        "destructiveHint",
                        getattr(ann, "destructive_hint", None),
                    ),
                }

            read_only = data.get("readOnlyHint", data.get("read_only_hint"))
            destructive = data.get("destructiveHint", data.get("destructive_hint"))

            if read_only is True:
                return False

            if destructive is True or read_only is False:
                return True

    return True


st.set_page_config(page_title="LM Studio MCP App")
st.title("LM Studio MCP App")

# Sidebar with user tools (clear chat/logs)
with st.sidebar:
    st.header("Settings")

    current_ws = str(WorkspaceManager.get_workspace())
    target_ws = st.text_input("Folder roboczy:", value=current_ws)

    if st.button("Zastosuj folder", use_container_width=True):
        try:
            applied = WorkspaceManager.set_workspace(target_ws)
            st.session_state.history = []
            st.session_state.pending_action = None
            st.success(f"Ustawiono: {applied.name}")
            st.rerun()
        except Exception as e:
            st.error(f"Błąd: {e}")

    st.caption("Aktualnie aktywna ścieżka:")
    st.caption(current_ws)

    st.divider()

    st.toggle(
        "Wymagaj potwierdzeń (HITL)",
        value=True,
        key="hitl_enabled",
        help="Gdy włączone, agent wymaga akceptacji przed wykonaniem operacji modyfikujących (zapis plików, commity, push).",
        disabled=(st.session_state.get("pending_action") is not None),
    )

    if not st.session_state.get("hitl_enabled", True):
        st.warning(
            "Tryb autonomiczny: Agent wykonuje wszystkie operacje bez pytania o zgodę."
        )

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


# Initialize conversation history in Streamlit session
if "history" not in st.session_state:
    st.session_state.history = []

if "pending_action" not in st.session_state:
    st.session_state.pending_action = None

if "resume_agent" not in st.session_state:
    st.session_state.resume_agent = False

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
        st.error(f"**Wymagana autoryzacja operacji:** `{action['name']}`")
        st.write("Sprawdź parametry przed zatwierdzeniem:")

        if action["name"] == "git_commit":
            st.info(f"**Wiadomość commita:** {action['args'].get('message')}")
            st.caption(
                f"Pliki: `{action['args'].get('files_to_add', '.')}` | Ścieżka: `{action['args'].get('repo_path', '.')}`"
            )
        elif action["name"] == "write_file":
            st.info(f"**Plik:** `{action['args'].get('file_path')}`")
            st.code(action["args"].get("content", ""), language="python")
        else:
            st.json(action["args"])

        col1, col2 = st.columns([1, 4])
        with col1:
            if st.button(
                "Zatwierdź i wykonaj", type="primary", use_container_width=True
            ):
                handle_pending_action(approved=True)
                st.rerun()
        with col2:
            if st.button("Odrzuć operację", use_container_width=True):
                handle_pending_action(approved=False)
                st.rerun()


# Block input while waiting for user decision
is_waiting_for_approval = st.session_state.pending_action is not None
prompt_placeholder = (
    "Wymagana decyzja powyżej..."
    if is_waiting_for_approval
    else "Wpisz polecenie dla asystenta..."
)


if st.session_state.resume_agent:
    st.session_state.resume_agent = False
    with st.chat_message("assistant"):
        ask_agent(None, st.session_state.history)
    st.rerun()

prompt = st.chat_input(prompt_placeholder, disabled=is_waiting_for_approval)

if prompt:
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        ask_agent(prompt, st.session_state.history)

    st.rerun()
