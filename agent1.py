# agent1.py

import os
import json
from dotenv import load_dotenv
from openai import OpenAI

# 从技能管理器导入
from skills import get_system_prompt, get_skill_info, list_all_skills, skill_manager
from tools import tools, available_functions

load_dotenv()

api_key = os.getenv('ZHIPU_API_KEY')
base_url = "https://open.bigmodel.cn/api/paas/v4/"
chat_model = "glm-4-flash"

client = OpenAI(
    api_key=api_key,
    base_url=base_url
)

print("✅ 环境配置成功！")

# ========== 全局变量 ==========
CURRENT_SKILL_NAME = "chun"  # 默认用"春"

# ========== 对话历史（核心） ==========
# 初始化时只有系统提示词
conversation_history = [
    {"role": "system", "content": get_system_prompt(CURRENT_SKILL_NAME)}
]
# ===================================


def get_current_prompt():
    """获取当前技能的提示词"""
    return get_system_prompt(CURRENT_SKILL_NAME)


def get_current_info():
    """获取当前技能的信息"""
    return get_skill_info(CURRENT_SKILL_NAME)


def switch_skill(skill_name):
    """切换技能并重置对话"""
    global CURRENT_SKILL_NAME, conversation_history
    if skill_manager.get_skill(skill_name):
        CURRENT_SKILL_NAME = skill_name
        # 切换技能时重置对话历史
        conversation_history = [
            {"role": "system", "content": get_system_prompt(CURRENT_SKILL_NAME)}
        ]
        return True
    return False


def run_conversation(user_input):
    """运行对话，自动维护上下文"""
    global conversation_history
    
    # 1. 添加用户消息到历史
    conversation_history.append({"role": "user", "content": user_input})
    
    # 2. 调用API（传入完整历史）
    response = client.chat.completions.create(
        model=chat_model,
        messages=conversation_history,
        tools=tools,
        tool_choice="auto",
    )
    
    response_message = response.choices[0].message
    
    # 3. 检查是否有工具调用
    tool_calls = response_message.tool_calls
    if tool_calls:
        # 先把模型的回复添加到历史
        conversation_history.append(response_message)
        
        for tool_call in tool_calls:
            function_name = tool_call.function.name
            function_args = json.loads(tool_call.function.arguments)
            
            function_to_call = available_functions[function_name]
            function_response = function_to_call(**function_args)
            
            # 添加工具结果到历史
            conversation_history.append({
                "tool_call_id": tool_call.id,
                "role": "tool",
                "name": function_name,
                "content": json.dumps(function_response),
            })
        
        # 再次调用API生成最终回答
        second_response = client.chat.completions.create(
            model=chat_model,
            messages=conversation_history,
        )
        final_message = second_response.choices[0].message
        conversation_history.append(final_message)
        return final_message.content
    else:
        # 没有工具调用，直接保存回复
        conversation_history.append(response_message)
        return response_message.content


def clear_history():
    """清空对话历史（保留系统提示词）"""
    global conversation_history
    conversation_history = [
        {"role": "system", "content": get_system_prompt(CURRENT_SKILL_NAME)}
    ]
    print("🧹 对话历史已清空")


def show_history():
    """显示对话历史摘要"""
    print(f"\n📜 对话历史（共 {len(conversation_history) - 1} 条消息）")
    print("-" * 50)
    for msg in conversation_history:
        if msg["role"] == "system":
            continue
        role_name = {"user": "👤 BOSS", "assistant": " 春"}.get(msg["role"], msg["role"])
        content = msg["content"][:60] + "..." if len(msg["content"]) > 60 else msg["content"]
        print(f"{role_name}: {content}")
    print("-" * 50)
    print()


if __name__ == "__main__":
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
        
        if user_input.lower() == 'exit':
            print("👋 再见，BOSS！")
            break
        
        # ====== 命令处理 ======
        if user_input.lower() == '/skills':
            print("\n📚 可用技能列表:")
            for skill in list_all_skills():
                status = "⭐ 当前" if skill['name'] == CURRENT_SKILL_NAME else "   "
                print(f"  {status} {skill['display_name']} - {skill['description']}")
            print()
            continue
        
        if user_input.startswith('/switch'):
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
        
        if user_input.lower() == '/clear':
            clear_history()
            print("✅ 已清空历史，可以重新开始对话\n")
            continue
        
        if user_input.lower() == '/history':
            show_history()
            continue
        # ========================
        
        # 正常对话
        response = run_conversation(user_input)
        print(f" {skill_info['display_name']}: {response}\n")
