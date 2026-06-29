# skills/__init__.py

from .base import Skill
from .chun import ChunSkill

class SkillManager:
    """技能管理器 - 负责加载和管理所有技能"""
    
    def __init__(self):
        self.skills = {}
        self._load_all_skills()
    
    def _load_all_skills(self):
        """加载所有已注册的技能"""
        # ========== 在这里注册你的所有技能 ==========
        all_skills = [
            ChunSkill,      # "春" - 你的主技能
            # 未来添加新技能时，在这里加一行：
            # FutureSkill1,
            # FutureSkill2,
        ]
        # ===========================================
        
        for skill_class in all_skills:
            skill = skill_class()
            self.skills[skill.name] = skill
            print(f"✅ 已加载技能: {skill.display_name}")
    
    def get_skill(self, name):
        """根据名称获取技能"""
        return self.skills.get(name)
    
    def get_default_skill(self):
        """获取默认技能（第一个）"""
        if self.skills:
            return list(self.skills.values())[0]
        return None
    
    def list_skills(self):
        """列出所有技能信息"""
        return [skill.get_info() for skill in self.skills.values()]
    
    def get_skill_names(self):
        """获取所有技能名称列表"""
        return list(self.skills.keys())


# 创建全局单例
skill_manager = SkillManager()


# ========== 便捷函数（供主程序调用） ==========
def get_system_prompt(skill_name=None):
    """获取指定技能的系统提示词，不传则返回默认"""
    if skill_name is None:
        skill = skill_manager.get_default_skill()
    else:
        skill = skill_manager.get_skill(skill_name)
    
    if skill:
        return skill.get_prompt()
    return None

def get_skill_info(skill_name=None):
    """获取技能信息"""
    if skill_name is None:
        skill = skill_manager.get_default_skill()
    else:
        skill = skill_manager.get_skill(skill_name)
    
    if skill:
        return skill.get_info()
    return None

def list_all_skills():
    """列出所有技能"""
    return skill_manager.list_skills()