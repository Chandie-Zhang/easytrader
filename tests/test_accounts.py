# coding: utf-8
"""测试 AccountManager 的核心逻辑（无需连接真实客户端）"""
import unittest
from unittest.mock import MagicMock

from easytrader.accounts import AccountManager


class MockTrader:
    """模拟 ClientTrader 对象"""
    def __init__(self):
        self._main = MagicMock()
        self._app = MagicMock()
        self._config = MagicMock()
        self.balance = {"资金余额": 100000, "可用金额": 80000, "总资产": 150000}
        self.position = [{"证券代码": "000001", "证券名称": "平安银行", "当前数量": 1000}]

    def buy(self, security, price, amount):
        return {"entrust_no": "123456"}

    def sell(self, security, price, amount):
        return {"entrust_no": "654321"}


def make_trader():
    return MockTrader()


class TestAccountManagerCore(unittest.TestCase):
    """测试 AccountManager 的核心逻辑"""

    def setUp(self):
        self.trader = make_trader()
        self.am = AccountManager(self.trader)
        # 直接注入测试账号，避免依赖 register / scan
        self.am._accounts = [
            {"name": "甲", "label": "甲", "hotkey": 1},
            {"name": "乙", "label": "乙", "hotkey": 2},
        ]
        self.am._active_index = 0

    def test_active_defaults_to_first(self):
        """默认活跃账号为第一个"""
        self.assertEqual(self.am.active, "甲")

    def test_switch_by_name(self):
        """switch() 按名称切换成功"""
        self.am.switch("乙")
        self.assertEqual(self.am.active, "乙")

    def test_switch_by_index(self):
        """switch() 按索引切换成功"""
        self.am.switch(1)
        self.assertEqual(self.am.active, "乙")

    def test_switch_same_account(self):
        """切换到当前账号不应重复发送快捷键"""
        self.am.switch("甲")
        self.assertEqual(self.am.active, "甲")
        self.trader._main.type_keys.assert_not_called()

    def test_switch_invalid_name(self):
        """切换不存在的名称应抛出 KeyError"""
        with self.assertRaises(KeyError):
            self.am.switch("不存在")

    def test_switch_invalid_index(self):
        """切换越界索引应抛出 KeyError"""
        with self.assertRaises(KeyError):
            self.am.switch(99)

    def test_getitem_chain(self):
        """__getitem__ 支持链式访问"""
        result = self.am["乙"]
        self.assertIs(result, self.am)
        self.assertEqual(self.am.active, "乙")

    def test_proxy_balance(self):
        """__getattr__ 代理 balance 到当前账号"""
        bal = self.am.balance
        self.assertEqual(bal["资金余额"], 100000)

    def test_proxy_buy(self):
        """__getattr__ 代理 buy() 到当前账号"""
        result = self.am.buy("000001", 10.0, 100)
        self.assertEqual(result["entrust_no"], "123456")

    def test_proxy_position(self):
        """__getattr__ 代理 position 到当前账号"""
        pos = self.am.position
        self.assertEqual(len(pos), 1)
        self.assertEqual(pos[0]["证券代码"], "000001")

    def test_proxy_no_accounts(self):
        """未注册账号时，代理直接走 trader 原始行为"""
        am = AccountManager(self.trader)
        bal = am.balance
        self.assertEqual(bal["资金余额"], 100000)

    def test_list_returns_accounts(self):
        """list() 返回账号列表"""
        result = self.am.list()
        self.assertEqual(len(result), 2)

    def test_switch_sends_hotkey(self):
        """switch() 应调用 type_keys 发送 ALT+数字"""
        self.am.switch("乙")
        self.trader._main.type_keys.assert_called_once_with("%2")

    def test_switch_only_sends_when_changed(self):
        """切换同名账号不应重复发送快捷键"""
        self.trader._main.type_keys.reset_mock()
        self.am.switch("甲")  # 已经是甲
        self.trader._main.type_keys.assert_not_called()

    def test_rename(self):
        """rename() 重命名账号"""
        self.am.rename(0, "new_name")
        self.assertEqual(self.am.accounts[0]["name"], "new_name")

    def test_rename_invalid_index(self):
        """rename() 越界索引应抛出 IndexError"""
        with self.assertRaises(IndexError):
            self.am.rename(99, "x")

    def test_match_by_label(self):
        """_resolve() 也匹配 label（原始扫描名）"""
        self.am._accounts.append({"name": "模拟", "label": "模拟炒股-UI**29", "hotkey": 3})
        self.am.switch("模拟炒股-UI**29")  # 按 label 匹配
        self.assertEqual(self.am.active, "模拟")


if __name__ == "__main__":
    unittest.main(verbosity=2)
