# coding:utf-8
import re
import time
from typing import Optional

from easytrader import exceptions
from easytrader.utils.market import get_security_market, MARKET_SH
from easytrader.utils.perf import perf_clock
from easytrader.utils.win_gui import SetForegroundWindow, ShowWindow, win32defines


class PopDialogHandler:
    def __init__(self, app):
        self._app = app
        self._dialog = None

    def _get_dialog(self):
        return self._dialog or self._app.top_window()

    @staticmethod
    def _set_foreground(window):
        # 兼容 WindowSpecification 与 wrapper 两种对象：
        # wrapper_object() 是 WindowSpecification 的方法，wrapper 对象直接用自身。
        wrapper = getattr(window, "wrapper_object", lambda: window)()
        if wrapper.has_style(win32defines.WS_MINIMIZE):  # 最小化时先还原
            ShowWindow(wrapper, 9)  # SW_RESTORE 还原窗口
        else:
            SetForegroundWindow(wrapper)  # 置前

    @perf_clock
    def handle(self, title, dialog=None):
        self._dialog = dialog
        if any(s in title for s in {"提示信息", "委托确认", "网上交易用户协议", "撤单确认"}):
            self._submit_by_shortcut()
            return None

        if "提示" in title:
            content = self._extract_content()
            self._submit_by_click()
            return {"message": content}

        content = self._extract_content()
        self._close()
        return {"message": "unknown message: {}".format(content)}

    def _extract_content(self):
        return self._get_dialog().Static.window_text()

    @staticmethod
    def _extract_entrust_id(content):
        return re.search(r"[\da-zA-Z]+", content).group()

    def _submit_by_click(self):
        try:
            self._get_dialog()["确定"].click()
        except Exception as ex:
            self._app.Window_(best_match="Dialog", top_level_only=True).ChildWindow(
                best_match="确定"
            ).click()

    def _submit_by_shortcut(self):
        dialog = self._get_dialog()
        self._set_foreground(dialog)
        dialog.type_keys("%Y", set_foreground=False)

    def _close(self):
        self._get_dialog().close()


class TradePopDialogHandler(PopDialogHandler):
    MARKET_SELECT_DIALOG_TITLE = "请选择证券市场"
    MARKET_SELECT_SH_BUTTON_CONTROL_ID = 1997
    MARKET_SELECT_SZ_BUTTON_CONTROL_ID = 1967
    MARKET_SELECT_REMEMBER_CONTROL_ID = 1504

    def __init__(self, app, security=None):
        super().__init__(app)
        self._security = security

    @staticmethod
    def _find_control(dialog, control_id):
        return next(
            (control for control in dialog.children() if control.control_id() == control_id),
            None,
        )

    def _handle_market_select_dialog(self):
        """处理“请选择证券市场”弹窗：取消记住选择，并按证券代码点击对应市场按钮"""
        market = get_security_market(self._security)
        if market is None:
            raise exceptions.TradeError("无法判断证券 {} 所属市场".format(self._security))

        dialog = self._get_dialog()
        remember = self._find_control(dialog, self.MARKET_SELECT_REMEMBER_CONTROL_ID)
        if remember is not None and remember.get_check_state():
            remember.send_message(win32defines.BM_CLICK)

        button_id = (
            self.MARKET_SELECT_SH_BUTTON_CONTROL_ID
            if market == MARKET_SH
            else self.MARKET_SELECT_SZ_BUTTON_CONTROL_ID
        )
        button = self._find_control(dialog, button_id)
        if button is None:
            raise exceptions.TradeError("选择市场弹窗中未找到 {} 按钮".format(market))
        button.send_message(win32defines.BM_CLICK)
        return None

    @perf_clock
    def handle(self, title, dialog=None) -> Optional[dict]:
        self._dialog = dialog
        if title == self.MARKET_SELECT_DIALOG_TITLE:
            return self._handle_market_select_dialog()

        if title == "委托确认":
            self._submit_by_shortcut()
            return None

        if title == "提示信息":
            content = self._extract_content()
            if "超出涨跌停" in content:
                self._submit_by_shortcut()
                return None

            if "委托价格的小数部分应为" in content:
                self._submit_by_shortcut()
                return None

            if "逆回购" in content:
                self._submit_by_shortcut()
                return None

            if "正回购" in content:
                self._submit_by_shortcut()
                return None

            return None

        if title == "提示":
            content = self._extract_content()
            if "成功" in content:
                entrust_no = self._extract_entrust_id(content)
                self._submit_by_click()
                return {"entrust_no": entrust_no}

            self._submit_by_click()
            time.sleep(0.05)
            raise exceptions.TradeError(content)
        self._close()
        return None
