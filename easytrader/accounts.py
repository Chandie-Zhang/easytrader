# -*- coding: utf-8 -*-
import time
from typing import Dict, List, Optional, Union

from easytrader.log import logger


class AccountManager:
    """
    多账号管理器 —— 管理同一个同花顺客户端内的多个已登录券商账号。
    
    单账号时自动降级为直通模式，所有操作直接作用于当前账号。
    
    用法::
    
        >>> import easytrader
        >>> trader = easytrader.use('universal')
        >>> trader.connect(exe_path='C:\\同花顺软件\\同花顺\\xiadan.exe')
        >>> am = easytrader.AccountManager(trader)
        >>> am.switch('账号1')            # ALT+1 切换
        >>> am.balance                    # 当前账号的资金
        >>> am['账号2'].buy('000001', 10, 100)  # 临时切换到账号2买入
    """

    def __init__(self, trader):
        self._trader = trader
        self._accounts: List[Dict] = []
        self._active_index: Optional[int] = None
        if trader._main is not None:
            try:
                self.scan()
            except Exception as e:
                logger.debug("自动扫描账号失败: %s", e)
        # 单账号兼容：扫描不到时创建默认账号，所有操作直通 trader
        if not self._accounts:
            self._accounts = [
                {"name": "当前账号", "hotkey": 1, "label": "", "_synthetic": True}
            ]
            self._active_index = 0
            logger.info("单账号模式: 操作将直接作用于当前已登录的账号")
    # ── 账号管理 ──────────────────────────────────────────────

    @property
    def accounts(self) -> List[Dict]:
        return list(self._accounts)

    @property
    def active(self) -> Optional[str]:
        if self._active_index is None:
            return None
        return self._accounts[self._active_index]["name"]

    @property
    def current(self) -> Optional[str]:
        """从同花顺界面实时读取当前选中的账号名称"""
        main = self._trader._main
        if main is None:
            return None
        try:
            combo = main.child_window(
                control_id=self._trader._config.ACCOUNT_SWITCHER_COMBOBOX_ID,
                class_name="ComboBox"
            )
            items = [it.strip() for it in combo.texts() if it and it.strip()]
            if not items:
                return None
            for acc in self._accounts:
                if acc["label"] == items[0]:
                    return acc["name"]
            return items[0]
        except Exception:
            return None

    def list(self) -> List[Dict]:
        if not self._accounts:
            return []
        single = len(self._accounts) == 1 and self._accounts[0].get("_synthetic")
        if single:
            logger.info("单账号模式: 当前已登录 1 个账号，无需切换")
            return self._accounts
        logger.info("已注册 %d 个账号:", len(self._accounts))
        for i, acc in enumerate(self._accounts):
            marker = " ← 当前" if i == self._active_index else ""
            logger.info("  [%d] %s (ALT+%d)%s", i + 1, acc["name"], acc["hotkey"], marker)
        return self._accounts

    # ── 自动扫描 ──────────────────────────────────────────────

    def scan(self) -> List[Dict]:
        main = self._trader._main
        if main is None:
            raise RuntimeError("请先调用 connect() 连接同花顺客户端后再扫描")

        raw = self._scan_account_manager_combobox(main)
        if not raw:
            return []

        self._accounts = [
            {
                "name": label.split("-")[0].strip() if "-" in label else label,
                "hotkey": i + 1,
                "label": label,
            }
            for i, label in enumerate(raw)
        ]
        if self._active_index is None and self._accounts:
            self._active_index = 0
        logger.info("扫描到 %d 个账号: %s", len(self._accounts),
                     [a["name"] for a in self._accounts])
        return self._accounts

    @staticmethod
    def _find_account_combobox_items(combo) -> Optional[List[str]]:
        raw_items = combo.texts()
        items = [it.strip() for it in raw_items if it and it.strip()]
        skip_keywords = ["编辑账户", "编辑账号", "添加", "管理"]
        real_accounts = []
        seen = set()
        for item in items:
            if any(kw in item for kw in skip_keywords):
                continue
            if item not in seen:
                seen.add(item)
                real_accounts.append(item)
        return real_accounts if len(real_accounts) >= 2 else None

    def _scan_account_manager_combobox(self, main) -> Optional[List[str]]:
        try:
            combo = main.child_window(
                control_id=self._trader._config.ACCOUNT_SWITCHER_COMBOBOX_ID,
                class_name="ComboBox"
            )
            # 快速检测控件是否存在，避免单账号时等待默认超时（~5s）
            if not combo.exists(timeout=0.5):
                return None
            return self._find_account_combobox_items(combo)
        except Exception:
            return None

    # ── 重命名 ──────────────────────────────────────────────

    def rename(self, index: int, new_name: str) -> "AccountManager":
        if index < 0 or index >= len(self._accounts):
            raise IndexError(
                f"账号索引 {index} 超出范围 (共 {len(self._accounts)} 个账号)"
            )
        self._accounts[index]["name"] = new_name
        logger.info("账号 [%d] 已重命名为: %s", index, new_name)
        return self

    # ── 账号切换 ──────────────────────────────────────────────

    def switch(self, name_or_index: Union[str, int]) -> "AccountManager":
        idx = self._resolve(name_or_index)
        if idx is None:
            available = ", ".join(
                [f"'{a['name']}'" for a in self._accounts]
            )
            raise KeyError(
                f"未找到账号: '{name_or_index}'，可用账号: [{available}]"
            )
        if idx == self._active_index:
            return self
        acc = self._accounts[idx]
        logger.info("切换到账号: %s", acc["name"])
        if not acc.get("_synthetic"):
            self._send_hotkey(acc["hotkey"])
        self._active_index = idx
        return self

    def _send_hotkey(self, hotkey: int):
        main = self._trader._main
        if main is None:
            raise RuntimeError("客户端未连接")
        try:
            main.set_focus()
        except Exception:
            pass
        time.sleep(0.2)
        main.type_keys("%{}".format(hotkey))
        time.sleep(0.5)

    def _resolve(self, name_or_index: Union[str, int]) -> Optional[int]:
        if isinstance(name_or_index, int):
            if 0 <= name_or_index < len(self._accounts):
                return name_or_index
            return None
        if isinstance(name_or_index, str):
            for i, acc in enumerate(self._accounts):
                if acc["name"] == name_or_index:
                    return i
            for i, acc in enumerate(self._accounts):
                if acc["label"] == name_or_index:
                    return i
        return None

    def __getitem__(self, name_or_index: Union[str, int]) -> "AccountManager":
        self.switch(name_or_index)
        return self

    # ── 操作代理 ──────────────────────────────────────────────

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        if not self._accounts:
            return getattr(self._trader, name)
        if self._active_index is None and self._accounts:
            self.switch(0)
        return getattr(self._trader, name)
