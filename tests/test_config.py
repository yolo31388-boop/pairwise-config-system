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
