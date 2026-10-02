"""配置系统 - 红态测试"""
import pytest, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.system import ConfigSystem

class TestTypeValidation:
    def test_invalid_type_rejected(self):
        cs = ConfigSystem()
        result = cs.load_config({"hp": "not_a_number"})
        assert result == False

class TestReloadNotify:
    def test_reload_notifies_listeners(self):
        cs = ConfigSystem()
        notified = []
        cs.listeners.append(lambda: notified.append(True))
        cs.reload_config({"hp": 100})
        assert len(notified) == 1

class TestDeepMerge:
    def test_nested_config_merged(self):
        cs = ConfigSystem()
        parent = {"graphics": {"quality": "high", "vsync": True}}
        child = {"graphics": {"quality": "low"}}
        result = cs.merge_config(parent, child)
        assert result["graphics"]["vsync"] == True

class TestValueRange:
    def test_value_out_of_range_rejected(self):
        cs = ConfigSystem()
        schema = {"hp": {"type": "int", "min": 0, "max": 100}}
        valid, msg = cs.validate_config({"hp": -10}, schema)
        assert valid == False

class TestExportFormat:
    def test_export_formatted(self):
        cs = ConfigSystem()
        result = cs.export_config({"a": 1, "b": 2})
        assert "\n" in result

class TestDefaultFilling:
    def test_missing_keys_filled_from_defaults(self):
        cs = ConfigSystem()
        cs.defaults = {"hp": 100, "mp": 50}
        assert cs.load_config({"hp": 80}) == True
        assert cs.config["mp"] == 50

class TestLoadFallback:
    def test_invalid_load_falls_back_to_defaults(self):
        cs = ConfigSystem()
        cs.defaults = {"hp": 100}
        assert cs.load_config({"hp": "bad"}) == False
        assert cs.config == {"hp": 100}

class TestReloadAtomic:
    def test_failed_reload_keeps_old_config(self):
        cs = ConfigSystem()
        cs.load_config({"hp": 100})
        cs.reload_config({"hp": "bad"})
        assert cs.config["hp"] == 100

class TestReloadChangeCheck:
    def test_unchanged_reload_skips_notify(self):
        cs = ConfigSystem()
        cs.load_config({"hp": 100})
        notified = []
        cs.listeners.append(lambda: notified.append(True))
        cs.reload_config({"hp": 100})
        assert len(notified) == 0

class TestReferences:
    def test_reference_resolved(self):
        cs = ConfigSystem()
        parent = {"base_hp": 100}
        child = {"boss_hp": "${base_hp}"}
        result = cs.merge_config(parent, child)
        assert result["boss_hp"] == 100

class TestCircularReference:
    def test_circular_reference_rejected(self):
        cs = ConfigSystem()
        with pytest.raises(ValueError):
            cs.merge_config({"a": "${b}"}, {"b": "${a}"})

class TestRequiredField:
    def test_missing_required_rejected(self):
        cs = ConfigSystem()
        schema = {"hp": {"type": "int", "required": True}}
        valid, msg = cs.validate_config({}, schema)
        assert valid == False

class TestErrorLocation:
    def test_error_message_has_location(self):
        cs = ConfigSystem()
        schema = {"player": {"schema": {"hp": {"type": "int", "min": 0}}}}
        valid, msg = cs.validate_config({"player": {"hp": -5}}, schema)
        assert valid == False
        assert "player.hp" in msg

class TestExportCommentAndSort:
    def test_export_keeps_comments_and_sorts(self):
        cs = ConfigSystem()
        result = cs.export_config({"_comment": "血量配置", "b": 2, "a": 1})
        assert "// 血量配置" in result
        assert result.index('"a"') < result.index('"b"')
