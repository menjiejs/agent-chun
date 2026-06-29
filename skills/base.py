# skills/base.py

class Skill:
    """技能基类"""
    
    def __init__(self):
        self.name = "base"
        self.display_name = "基础技能"
        self.description = "默认的基础技能"
        self.system_prompt = "你是一个智能助手。"
        self.version = "1.0"
        self.author = "unknown"
    
    def get_prompt(self):
        return self.system_prompt
    
    def get_info(self):
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "version": self.version,
            "author": self.author
        }