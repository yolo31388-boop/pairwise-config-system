"""配置系统 - 含5个bug"""
from dataclasses import dataclass, field

class ConfigSystem:
    def __init__(self):
        self.config: dict = {}
        self.defaults: dict = {}
        self.listeners: list = []

    def load_config(self, data: dict) -> bool:
        # bug1: 不做类型校验，无默认值
        self.config = data
        return True

    def reload_config(self, new_data: dict) -> None:
        # bug2: 不通知，非原子
        self.config = new_data

    def merge_config(self, parent: dict, child: dict) -> dict:
        # bug3: 浅合并，无引用
        result = parent.copy()
        result.update(child)
        return result

    def validate_config(self, data: dict, schema: dict) -> tuple:
        # bug4: 只检查key存在
        for key in schema:
            if key not in data:
                return False, f"Missing key: {key}"
        return True, ""

    def export_config(self, data: dict) -> str:
        # bug5: 不保留注释，不格式化
        import json
        return json.dumps(data)
