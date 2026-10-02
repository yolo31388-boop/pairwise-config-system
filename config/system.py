"""配置系统：加载校验、热重载、继承合并、验证、导出。"""
import copy
import json
import re
import threading


class ConfigSystem:
    _REF_PATTERN = re.compile(r"^\$\{([^}]+)\}$")
    _REF_PREFIX = "$ref:"

    _TYPE_MAP = {
        "int": int, "integer": int,
        "float": (int, float), "number": (int, float),
        "str": str, "string": str,
        "bool": bool, "boolean": bool,
        "list": list, "array": list,
        "dict": dict, "object": dict,
    }
    _SCHEMA_KEYS = ("type", "min", "max", "required", "enum")

    # 游戏代码内置期望的类型（代码侧契约）
    _BUILTIN_TYPES = {
        "hp": int, "max_hp": int, "mp": int, "max_mp": int,
        "level": int, "exp": int, "attack": int, "defense": int,
        "gold": int, "speed": (int, float), "volume": (int, float),
    }

    def __init__(self):
        self.config: dict = {}
        self.defaults: dict = {}
        self.listeners: list = []
        self._lock = threading.RLock()

    # ---------- 加载 ----------
    def load_config(self, data: dict) -> bool:
        """加载配置：类型校验 + 默认值填充，失败回退到默认配置。"""
        if not isinstance(data, dict) or not self._check_types(data):
            self._fallback_to_defaults()
            return False
        with self._lock:
            self.config = self._deep_merge(self.defaults, data)
        return True

    def _fallback_to_defaults(self) -> None:
        with self._lock:
            self.config = copy.deepcopy(self.defaults)

    def _expected_type(self, key):
        if key in self.defaults and self.defaults[key] is not None:
            return type(self.defaults[key])
        return self._BUILTIN_TYPES.get(key)

    def _check_types(self, data: dict) -> bool:
        for key, value in data.items():
            expected = self._expected_type(key)
            if expected is not None and not self._is_instance(value, expected):
                return False
        return True

    @staticmethod
    def _is_instance(value, expected) -> bool:
        types = list(expected) if isinstance(expected, tuple) else [expected]
        if float in types and int not in types:
            types.append(int)
        if isinstance(value, bool) and bool not in types:
            return False
        return isinstance(value, tuple(types))

    # ---------- 热重载 ----------
    def reload_config(self, new_data: dict) -> bool:
        """热重载：校验后原子替换，无变化则跳过，成功后通知监听者。"""
        if not isinstance(new_data, dict) or not self._check_types(new_data):
            return False
        candidate = self._deep_merge(self.defaults, new_data)
        with self._lock:
            if candidate == self.config:
                return False
            self.config = candidate  # 原子替换，读取方不会看到中间态
        for listener in list(self.listeners):
            listener()
        return True

    # ---------- 继承合并 ----------
    def merge_config(self, parent: dict, child: dict) -> dict:
        """递归深合并，并解析 ${path} / $ref:path 引用，检测循环引用。"""
        merged = self._deep_merge(parent, child)
        return self._resolve_refs(merged)

    def _deep_merge(self, base: dict, override: dict) -> dict:
        result = copy.deepcopy(base)
        for key, value in override.items():
            if isinstance(result.get(key), dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = copy.deepcopy(value)
        return result

    def _match_ref(self, value):
        if not isinstance(value, str):
            return None
        match = self._REF_PATTERN.match(value)
        if match:
            return match.group(1).strip()
        if value.startswith(self._REF_PREFIX):
            return value[len(self._REF_PREFIX):].strip()
        return None

    def _resolve_refs(self, config: dict) -> dict:
        resolving: set = set()
        cache: dict = {}

        def lookup(path):
            node = config
            for part in path.split("."):
                if not isinstance(node, dict) or part not in node:
                    raise ValueError(f"无法解析的配置引用: {path}")
                node = node[part]
            return node

        def resolve_ref(path):
            if path in cache:
                return cache[path]
            if path in resolving:
                raise ValueError(f"检测到循环引用: {path}")
            resolving.add(path)
            resolved = resolve_value(lookup(path), path)
            resolving.discard(path)
            cache[path] = resolved
            return resolved

        def resolve_value(value, path):
            if isinstance(value, dict):
                return {
                    k: resolve_value(v, f"{path}.{k}" if path else k)
                    for k, v in value.items()
                }
            if isinstance(value, list):
                return [resolve_value(item, path) for item in value]
            ref = self._match_ref(value)
            if ref is not None:
                return resolve_ref(ref)
            return value

        return resolve_value(config, "")

    # ---------- 验证 ----------
    def validate_config(self, data: dict, schema: dict) -> tuple:
        """按 schema 验证：类型、取值范围、必填项，错误信息带配置路径。"""
        errors: list = []
        self._validate(data, schema, "", errors)
        return (not errors), "; ".join(errors)

    def _validate(self, data, schema, path, errors) -> None:
        if not isinstance(data, dict):
            errors.append(f"{path or '<root>'}: 期望字典，实际 {type(data).__name__}")
            return
        for key, rule in schema.items():
            loc = f"{path}.{key}" if path else key
            if isinstance(rule, dict) and not any(k in self._SCHEMA_KEYS for k in rule):
                if key not in data:
                    errors.append(f"缺少必填项: {loc}")
                else:
                    self._validate(data[key], rule, loc, errors)
                continue
            self._validate_rule(data, key, rule, loc, errors)

    def _validate_rule(self, data, key, rule, loc, errors) -> None:
        if not isinstance(rule, dict):
            rule = {"type": rule}
        if key not in data:
            if rule.get("required", True):
                errors.append(f"缺少必填项: {loc}")
            return
        value = data[key]
        expected = rule.get("type")
        if expected is not None:
            types = self._TYPE_MAP.get(expected, expected) if isinstance(expected, str) else expected
            if not self._is_instance(value, types):
                errors.append(
                    f"{loc}: 类型错误，期望 {expected}，实际 {type(value).__name__}"
                )
                return
        is_number = isinstance(value, (int, float)) and not isinstance(value, bool)
        if "min" in rule and is_number and value < rule["min"]:
            errors.append(f"{loc}: 值 {value} 小于最小值 {rule['min']}")
        if "max" in rule and is_number and value > rule["max"]:
            errors.append(f"{loc}: 值 {value} 大于最大值 {rule['max']}")
        if "enum" in rule and value not in rule["enum"]:
            errors.append(f"{loc}: 值 {value!r} 不在可选范围 {rule['enum']}")

    # ---------- 导出 ----------
    def export_config(self, data: dict, comments: dict = None) -> str:
        """导出配置：键排序、缩进格式化，按路径保留注释（// 形式）。

        comments: {"graphics.quality": "画质"}；数据中的 "_comment" 键也会
        作为所在字典的注释导出。
        """
        comments = comments or {}

        def render(value, level, path):
            indent = "  " * level
            child_indent = "  " * (level + 1)
            if isinstance(value, dict):
                if not value:
                    return "{}"
                lines = ["{"]
                own_comment = value.get("_comment")
                if isinstance(own_comment, str):
                    lines.append(f"{child_indent}// {own_comment}")
                items = sorted(
                    (k, v) for k, v in value.items() if k != "_comment"
                )
                for index, (key, val) in enumerate(items):
                    child_path = f"{path}.{key}" if path else key
                    comment = comments.get(child_path)
                    if comment:
                        for comment_line in str(comment).splitlines():
                            lines.append(f"{child_indent}// {comment_line}")
                    comma = "," if index < len(items) - 1 else ""
                    rendered = render(val, level + 1, child_path)
                    lines.append(
                        f"{child_indent}{json.dumps(key, ensure_ascii=False)}: "
                        f"{rendered}{comma}"
                    )
                lines.append(f"{indent}}}")
                return "\n".join(lines)
            if isinstance(value, list):
                if not value:
                    return "[]"
                lines = ["["]
                for index, item in enumerate(value):
                    comma = "," if index < len(value) - 1 else ""
                    lines.append(f"{child_indent}{render(item, level + 1, path)}{comma}")
                lines.append(f"{indent}]")
                return "\n".join(lines)
            return json.dumps(value, ensure_ascii=False)

        return render(data, 0, "")
