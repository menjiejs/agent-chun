import json
import os
import threading

from openai import OpenAI

from app.history_store import (
    append_message,
    clear_messages,
    get_or_create_session,
    init_db,
    load_messages,
    update_session_skill,
)
from skills import get_skill_info, get_system_prompt, list_all_skills, skill_manager
from tools import available_functions, tools
from app.config import load_configuration


load_configuration()
init_db()

api_key = os.getenv("ZHIPU_API_KEY")
base_url = "https://open.bigmodel.cn/api/paas/v4/"
chat_model = "glm-4-flash"

client = OpenAI(api_key=api_key, base_url=base_url)

print("✅ 环境配置成功！")

DEFAULT_SESSION_ID = "default"
DEFAULT_SKILL_NAME = "chun"

_sessions = {}
_sessions_lock = threading.RLock()


def _message_to_dict(message):
    if isinstance(message, dict):
        return message

    data = {
        "role": message.role,
        "content": message.content,
    }
    if getattr(message, "tool_calls", None):
        data["tool_calls"] = [
            {
                "id": tool_call.id,
                "type": tool_call.type,
                "function": {
                    "name": tool_call.function.name,
                    "arguments": tool_call.function.arguments,
                },
            }
            for tool_call in message.tool_calls
        ]
    return data


def _build_system_message(skill_name):
    return {"role": "system", "content": get_system_prompt(skill_name)}


def _get_session_state(session_id=DEFAULT_SESSION_ID):
    with _sessions_lock:
        if session_id in _sessions:
            return _sessions[session_id]

        session = get_or_create_session(session_id, DEFAULT_SKILL_NAME)
        skill_name = session["skill_name"]
        messages = [_build_system_message(skill_name)]
        messages.extend(load_messages(session_id))
        _sessions[session_id] = {
            "session_id": session_id,
            "skill_name": skill_name,
            "messages": messages,
        }
        return _sessions[session_id]


def _append_session_message(session_id, message, persist=True):
    state = _get_session_state(session_id)
    state["messages"].append(message)
    if persist and message.get("role") != "system":
        append_message(session_id, message)


def get_current_info(session_id=DEFAULT_SESSION_ID):
    state = _get_session_state(session_id)
    return get_skill_info(state["skill_name"])


def get_current_prompt(session_id=DEFAULT_SESSION_ID):
    state = _get_session_state(session_id)
    return get_system_prompt(state["skill_name"])


def list_skills():
    return list_all_skills()


def switch_skill(skill_name, session_id=DEFAULT_SESSION_ID):
    if not skill_manager.get_skill(skill_name):
        return False

    with _sessions_lock:
        update_session_skill(session_id, skill_name)
        clear_messages(session_id)
        _sessions[session_id] = {
            "session_id": session_id,
            "skill_name": skill_name,
            "messages": [_build_system_message(skill_name)],
        }
    return True


def run_conversation(user_input, session_id=DEFAULT_SESSION_ID):
    user_message = {"role": "user", "content": user_input}
    _append_session_message(session_id, user_message)

    state = _get_session_state(session_id)
    response = client.chat.completions.create(
        model=chat_model,
        messages=state["messages"],
        tools=tools,
        tool_choice="auto",
    )

    response_message = response.choices[0].message
    assistant_message = _message_to_dict(response_message)
    tool_calls = assistant_message.get("tool_calls")

    if tool_calls:
        _append_session_message(session_id, assistant_message)

        for tool_call in tool_calls:
            function_name = tool_call["function"]["name"]
            function_args = json.loads(tool_call["function"]["arguments"])
            function_to_call = available_functions[function_name]
            function_response = function_to_call(**function_args)

            tool_message = {
                "tool_call_id": tool_call["id"],
                "role": "tool",
                "name": function_name,
                "content": json.dumps(function_response, ensure_ascii=False),
            }
            _append_session_message(session_id, tool_message)

        second_response = client.chat.completions.create(
            model=chat_model,
            messages=_get_session_state(session_id)["messages"],
        )
        final_message = _message_to_dict(second_response.choices[0].message)
        _append_session_message(session_id, final_message)
        return final_message.get("content", "")

    _append_session_message(session_id, assistant_message)
    return assistant_message.get("content", "")


def stream_conversation(user_input, session_id=DEFAULT_SESSION_ID):
    user_message = {"role": "user", "content": user_input}
    _append_session_message(session_id, user_message)

    chunks = []
    state = _get_session_state(session_id)
    stream = client.chat.completions.create(
        model=chat_model,
        messages=state["messages"],
        stream=True,
    )

    for event in stream:
        delta = event.choices[0].delta
        content = getattr(delta, "content", None)
        if content:
            chunks.append(content)
            yield content

    assistant_message = {"role": "assistant", "content": "".join(chunks)}
    _append_session_message(session_id, assistant_message)


def clear_history(session_id=DEFAULT_SESSION_ID):
    state = _get_session_state(session_id)
    clear_messages(session_id)
    state["messages"] = [_build_system_message(state["skill_name"])]
    print("🧹 对话历史已清空")


def show_history(session_id=DEFAULT_SESSION_ID):
    state = _get_session_state(session_id)
    messages = state["messages"]
    print(f"\n📜 对话历史（共 {len(messages) - 1} 条消息）")
    print("-" * 50)
    for msg in messages:
        if msg["role"] == "system":
            continue
        role_name = {"user": "👤 BOSS", "assistant": " 春"}.get(
            msg["role"], msg["role"]
        )
        content = msg.get("content") or ""
        content = content[:60] + "..." if len(content) > 60 else content
        print(f"{role_name}: {content}")
    print("-" * 50)
    print()


def main():
    skill_info = get_current_info()

    print("=" * 50)
    print(f" 当前技能: {skill_info['display_name']}")
    print(f"📝 {skill_info['description']}")
    print("=" * 50)
    print("💡 命令:")
    print("  /skills      - 查看所有可用技能")
    print("  /switch 名称 - 切换技能（自动清空历史）")
    print("  /clear       - 清空对话历史")
    print("  /history     - 查看对话历史")
    print("  exit         - 退出")
    print("=" * 50)
    print()

    while True:
        user_input = input("👤 BOSS: ")

        if user_input.lower() == "exit":
            print("👋 再见，BOSS！")
            break

        if user_input.lower() == "/skills":
            print("\n📚 可用技能列表:")
            current_skill_name = get_current_info()["name"]
            for skill in list_skills():
                status = "⭐ 当前" if skill["name"] == current_skill_name else "   "
                print(f"  {status} {skill['display_name']} - {skill['description']}")
            print()
            continue

        if user_input.startswith("/switch"):
            parts = user_input.split()
            if len(parts) >= 2:
                new_skill = parts[1]
                if switch_skill(new_skill):
                    skill_info = get_current_info()
                    print(f"✅ 已切换到: {skill_info['display_name']}")
                    print(f"📝 {skill_info['description']}")
                    print("🔄 对话历史已重置\n")
                else:
                    print(f"❌ 技能 '{new_skill}' 不存在。输入 /skills 查看所有技能\n")
            else:
                print("❌ 用法: /switch [技能名]\n")
            continue

        if user_input.lower() == "/clear":
            clear_history()
            print("✅ 已清空历史，可以重新开始对话\n")
            continue

        if user_input.lower() == "/history":
            show_history()
            continue

        response = run_conversation(user_input)
        print(f" {get_current_info()['display_name']}: {response}\n")


if __name__ == "__main__":
    main()
