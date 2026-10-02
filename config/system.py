"""配置系统"""
import copy
import json
import re


class ConfigSystem:
    BUILTIN_SCHEMA = {
        "hp": {"type": "int", "min": 0},
        "mp": {"type": "int", "min": 0},
        "level": {"type": "int", "min": 1},
        "speed": {"type": "float", "min": 0},
        "volume": {"type": "int", "min": 0, "max": 100},
        "name": {"type": "str"},
        "debug": {"type": "bool"},
    }

    SIMPLE_TYPES = {"str": str, "bool": bool, "list": list, "dict": dict}

    REF_PATTERN = re.compile(r"^\$\{([^}]+)\}$")

    def __init__(self):
        self.config: dict = {}
        self.defaults: dict = {}
        self.schema: dict = dict(self.BUILTIN_SCHEMA)
        self.listeners: list = []

    def load_config(self, data: dict) -> bool:
        if not isinstance(data, dict):
            self.config = copy.deepcopy(self.defaults)
            return False
        valid, _msg = self.validate_config(data, self._effective_schema())
        if not valid:
            self.config = copy.deepcopy(self.defaults)
            return False
        self.config = self._fill_defaults(data)
        return True

    def reload_config(self, new_data: dict) -> None:
        if not isinstance(new_data, dict):
            return
        valid, _msg = self.validate_config(new_data, self._effective_schema())
        if not valid:
            return
        candidate = self._fill_defaults(new_data)
        if candidate == self.config:
            return
        self.config = candidate
        for listener in list(self.listeners):
            listener()

    def merge_config(self, parent: dict, child: dict) -> dict:
        merged = self._deep_merge(copy.deepcopy(parent), copy.deepcopy(child))
        return self._resolve_references(merged)

    def validate_config(self, data: dict, schema: dict) -> tuple:
        errors: list = []
        self._validate(data, schema, "", errors)
        if errors:
            return False, "; ".join(errors)
        return True, ""

    def export_config(self, data: dict) -> str:
        raw = json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True)
        lines = []
        for line in raw.splitlines():
            stripped = line.lstrip()
            indent = line[: len(line) - len(stripped)]
            match = re.match(r'"_comment[^"]*":\s*("(?:[^"\\]|\\.)*"),?$', stripped)
            if match:
                lines.append(f"{indent}// {json.loads(match.group(1))}")
            else:
                lines.append(line)
        return "\n".join(lines) + "\n"

    def _effective_schema(self) -> dict:
        schema = copy.deepcopy(self.schema)
        for key, default in self.defaults.items():
            if key not in schema and default is not None:
                schema[key] = {"type": type(default).__name__}
            if isinstance(default, dict) and key in schema:
                nested = {k: {"type": type(v).__name__} for k, v in default.items()
                          if v is not None}
                schema[key].setdefault("schema", nested)
        return schema

    def _fill_defaults(self, data: dict) -> dict:
        return self._deep_merge(copy.deepcopy(self.defaults), data)

    def _deep_merge(self, base: dict, override: dict) -> dict:
        result = dict(base)
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def _resolve_references(self, config: dict) -> dict:
        def get_path(path: str):
            node = config
            for part in path.split("."):
                if not isinstance(node, dict) or part not in node:
                    raise KeyError(f"Reference not found: {path}")
                node = node[part]
            return node

        def resolve(node, chain: list):
            if isinstance(node, dict):
                return {key: resolve(value, chain) for key, value in node.items()}
            if isinstance(node, list):
                return [resolve(item, chain) for item in node]
            if isinstance(node, str):
                match = self.REF_PATTERN.match(node)
                if not match:
                    return node
                ref = match.group(1)
                if ref in chain:
                    raise ValueError(
                        "Circular reference detected: " + " -> ".join(chain + [ref])
                    )
                chain.append(ref)
                try:
                    return resolve(get_path(ref), chain)
                finally:
                    chain.pop()
            return node

        return resolve(config, [])

    def _validate(self, data: dict, schema: dict, path: str, errors: list) -> None:
        if not isinstance(data, dict):
            errors.append(f"{path or '<root>'}: expected dict, got {type(data).__name__}")
            return
        for key, rules in schema.items():
            if not isinstance(rules, dict):
                continue
            location = f"{path}.{key}" if path else key
            if key not in data:
                if rules.get("required", False):
                    errors.append(f"{location}: missing required field")
                continue
            value = data[key]
            expected = rules.get("type")
            if expected and not self._check_type(value, expected):
                errors.append(
                    f"{location}: expected {expected}, got {type(value).__name__}"
                )
                continue
            self._check_range(value, rules, location, errors)
            choices = rules.get("choices")
            if choices is not None and value not in choices:
                errors.append(f"{location}: value {value!r} not in {choices}")
            nested = rules.get("schema")
            if nested and isinstance(value, dict):
                self._validate(value, nested, location, errors)

    def _check_type(self, value, expected: str) -> bool:
        if expected == "int":
            return isinstance(value, int) and not isinstance(value, bool)
        if expected == "float":
            return isinstance(value, (int, float)) and not isinstance(value, bool)
        pytype = self.SIMPLE_TYPES.get(expected)
        if pytype is None:
            return True
        return isinstance(value, pytype)

    def _check_range(self, value, rules: dict, location: str, errors: list) -> None:
        if isinstance(value, bool):
            return
        if isinstance(value, (int, float)):
            measured = value
        elif isinstance(value, (str, list)):
            measured = len(value)
        else:
            return
        if "min" in rules and measured < rules["min"]:
            errors.append(f"{location}: value {value!r} below min {rules['min']}")
        if "max" in rules and measured > rules["max"]:
            errors.append(f"{location}: value {value!r} above max {rules['max']}")
