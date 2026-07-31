# -*- coding: utf-8 -*-
import abc
import functools
import logging
import os
import re
import sys
import time
from typing import Type, Union

import hashlib, binascii

import easyutils
from pywinauto import findwindows, timings

from easytrader import grid_strategies, pop_dialog_handler, refresh_strategies
from easytrader.client_lock import ClientOperationLock, locked_client_operation
from easytrader.config import client
from easytrader.grid_strategies import IGridStrategy
from easytrader.log import logger
from easytrader.utils.misc import file2dict
from easytrader.utils.perf import perf_clock

if not sys.platform.startswith("darwin"):
    import pywinauto
    import pywinauto.clipboard
    from easytrader.utils.win_gui import (
        SetForegroundWindow,
        ShowWindow,
        win32defines,
    )


class IClientTrader(abc.ABC):
    @property
    @abc.abstractmethod
    def app(self):
        """Return current app instance"""
        pass

    @property
    @abc.abstractmethod
    def main(self):
        """Return current main window instance"""
        pass

    @property
    @abc.abstractmethod
    def config(self):
        """Return current config instance"""
        pass

    @abc.abstractmethod
    def wait(self, seconds: float):
        """Wait for operation return"""
        pass

    @abc.abstractmethod
    def refresh(self):
        """Refresh data"""
        pass

    @abc.abstractmethod
    def is_exist_pop_dialog(self):
        pass


class ClientTrader(IClientTrader):
    _editor_need_type_keys = False
    # The strategy to use for getting grid data
    grid_strategy: Union[IGridStrategy, Type[IGridStrategy]] = grid_strategies.Copy
    _grid_strategy_instance: IGridStrategy = None

    def enable_type_keys_for_editor(self):
        """
        有些客户端无法通过 set_edit_text 方法输入内容，可以通过使用 type_keys 方法绕过
        """
        self._editor_need_type_keys = True

    @property
    def grid_strategy_instance(self):
        if self._grid_strategy_instance is None:
            self._grid_strategy_instance = (
                self.grid_strategy
                if isinstance(self.grid_strategy, IGridStrategy)
                else self.grid_strategy()
            )
            self._grid_strategy_instance.set_trader(self)
        return self._grid_strategy_instance

    def __init__(self):
        self._config = client.create(self.broker_type)
        self._app = None
        self._main = None
        self._toolbar = None
        self._grid_strategy_instance = None
        self.refresh_strategy = refresh_strategies.Switch()
        self._client_lock = ClientOperationLock()

    @property
    def app(self):
        return self._app

    @property
    def main(self):
        return self._main

    @property
    def config(self):
        return self._config

    def connect(self, exe_path=None, **kwargs):
        """
        直接连接登陆后的客户端
        :param exe_path: 客户端路径类似 r'C:\\htzqzyb2\\xiadan.exe', 默认 r'C:\\htzqzyb2\\xiadan.exe'
        :return:
        """
        connect_path = exe_path or self._config.DEFAULT_EXE_PATH
        if connect_path is None:
            raise ValueError(
                "参数 exe_path 未设置，请设置客户端对应的 exe 地址,类似 C:\\客户端安装目录\\xiadan.exe"
            )

        self._client_lock.configure(self._operation_lock_path(connect_path))
        with self._client_lock.operation("connect"):
            self._app = pywinauto.Application().connect(path=connect_path, timeout=10)
            self._close_prompt_windows()
            self._main = self._app.top_window()
            self._init_toolbar()

    @property
    def broker_type(self):
        return "ths"

    @property
    @locked_client_operation
    def balance(self):
        self._switch_left_menus(["查询[F4]", "资金股票"])

        return self._get_balance_from_statics()

    def _init_toolbar(self):
        self._toolbar = self._main.child_window(class_name="ToolbarWindow32")

    def _get_balance_from_statics(self):
        result = {}
        for key, control_id in self._config.BALANCE_CONTROL_ID_GROUP.items():
            result[key] = float(
                self._main.child_window(
                    control_id=control_id, class_name="Static"
                ).window_text()
            )
        return result

    @property
    @locked_client_operation
    def position(self):
        self._switch_left_menus(["查询[F4]", "资金股票"])
        self.refresh()
        return self._get_grid_data(self._config.COMMON_GRID_CONTROL_ID)

    @property
    @locked_client_operation
    def today_entrusts(self):
        self._switch_left_menus(["查询[F4]", "当日委托"])
        self.refresh()
        return self._get_grid_data(self._config.COMMON_GRID_CONTROL_ID)

    @property
    @locked_client_operation
    def today_trades(self):
        self._switch_left_menus(["查询[F4]", "当日成交"])
        self.refresh()
        return self._get_grid_data(self._config.COMMON_GRID_CONTROL_ID)

    @locked_client_operation
    def history_entrusts(self, start_date=None, end_date=None):
        """
        查询历史委托记录（默认返回客户端显示的委托数据）
        :param start_date: 保留参数，当前版本客户端不支持自定义日期筛选
        :param end_date: 保留参数，当前版本客户端不支持自定义日期筛选
        :return: list of dict
        """
        return self._query_history(self._config.HISTORY_ENTRUSTS_MENU_PATH)

    @locked_client_operation
    def history_trades(self, start_date=None, end_date=None):
        """
        查询历史成交记录（默认返回客户端显示的成交数据）
        :param start_date: 保留参数，当前版本客户端不支持自定义日期筛选
        :param end_date: 保留参数，当前版本客户端不支持自定义日期筛选
        :return: list of dict
        """
        return self._query_history(self._config.HISTORY_TRADES_MENU_PATH)

    @locked_client_operation
    def exchangebill(self, start_date=None, end_date=None):
        """
        查询交割单（默认返回客户端显示的最近30天交割单）
        :param start_date: 保留参数，当前版本客户端不支持自定义日期筛选
        :param end_date: 保留参数，当前版本客户端不支持自定义日期筛选
        :return: list of dict
        """
        return self._query_history(self._config.EXCHANGEBILL_MENU_PATH)

    @property
    @locked_client_operation
    def cancel_entrusts(self):
        self.refresh()
        self._switch_left_menus(["撤单[F3]"])

        return self._get_grid_data(self._config.COMMON_GRID_CONTROL_ID)

    @perf_clock
    @locked_client_operation
    def cancel_entrust(self, entrust_no):
        self.refresh()
        for i, entrust in enumerate(self.cancel_entrusts):
            if entrust[self._config.CANCEL_ENTRUST_ENTRUST_FIELD] == entrust_no:
                self._cancel_entrust_by_double_click(i)
                return self._handle_pop_dialogs()
        return {"message": "委托单状态错误不能撤单, 该委托单可能已经成交或者已撤"}

    @locked_client_operation
    def cancel_all_entrusts(self):
        self.refresh()
        self._switch_left_menus(["撤单[F3]"])

        # 点击全部撤销控件
        self._app.top_window().child_window(
            control_id=self._config.TRADE_CANCEL_ALL_ENTRUST_CONTROL_ID,
            class_name="Button",
            title_re="""全撤.*""",
        ).click()
        self.wait(0.2)

        # 等待出现 确认兑换框
        if self.is_exist_pop_dialog():
            # 点击是 按钮
            w = self._app.top_window()
            if w is not None:
                btn = w["是(Y)"]
                if btn is not None:
                    btn.click()
                    self.wait(0.2)

        # 如果出现了确认窗口
        self.close_pop_dialog()

    @perf_clock
    @locked_client_operation
    def repo(self, security, price, amount, **kwargs):
        self._switch_left_menus(["债券回购", "融资回购（正回购）"])

        return self.trade(security, price, amount)

    @perf_clock
    @locked_client_operation
    def reverse_repo(self, security, price, amount, **kwargs):
        self._switch_left_menus(["债券回购", "融劵回购（逆回购）"])

        return self.trade(security, price, amount)

    @perf_clock
    @locked_client_operation
    def buy(self, security, price, amount, **kwargs):
        self._switch_left_menus(["买入[F1]"])

        return self.trade(security, price, amount)

    @perf_clock
    @locked_client_operation
    def sell(self, security, price, amount, **kwargs):
        self._switch_left_menus(["卖出[F2]"])

        return self.trade(security, price, amount)

    @perf_clock
    @locked_client_operation
    def market_buy(self, security, amount, ttype=None, limit_price=None, **kwargs):
        """
        市价买入
        :param security: 六位证券代码
        :param amount: 交易数量
        :param ttype: 市价委托类型，默认客户端默认选择，
                     深市可选 ['对手方最优价格', '本方最优价格', '即时成交剩余撤销', '最优五档即时成交剩余 '全额成交或撤销']
                     沪市可选 ['最优五档成交剩余撤销', '最优五档成交剩余转限价']
        :param limit_price: 科创板 限价

        :return: {'entrust_no': '委托单号'}
        """
        self._switch_left_menus(["市价委托", "买入"])

        return self.market_trade(security, amount, ttype, limit_price=limit_price)

    @perf_clock
    @locked_client_operation
    def market_sell(self, security, amount, ttype=None, limit_price=None, **kwargs):
        """
        市价卖出
        :param security: 六位证券代码
        :param amount: 交易数量
        :param ttype: 市价委托类型，默认客户端默认选择，
                     深市可选 ['对手方最优价格', '本方最优价格', '即时成交剩余撤销', '最优五档即时成交剩余 '全额成交或撤销']
                     沪市可选 ['最优五档成交剩余撤销', '最优五档成交剩余转限价']
        :param limit_price: 科创板 限价
        :return: {'entrust_no': '委托单号'}
        """
        self._switch_left_menus(["市价委托", "卖出"])

        return self.market_trade(security, amount, ttype, limit_price=limit_price)

    @locked_client_operation
    def market_trade(self, security, amount, ttype=None, limit_price=None, **kwargs):
        """
        市价交易
        :param security: 六位证券代码
        :param amount: 交易数量
        :param ttype: 市价委托类型，默认客户端默认选择，
                     深市可选 ['对手方最优价格', '本方最优价格', '即时成交剩余撤销', '最优五档即时成交剩余 '全额成交或撤销']
                     沪市可选 ['最优五档成交剩余撤销', '最优五档成交剩余转限价']

        :return: {'entrust_no': '委托单号'}
        """
        code = security[-6:]
        self._type_edit_control_keys(self._config.TRADE_SECURITY_CONTROL_ID, code)
        self._handle_market_select_dialog(security)
        if ttype is not None:
            retry = 0
            retry_max = 10
            while retry < retry_max:
                try:
                    self._set_market_trade_type(ttype)
                    break
                except:
                    retry += 1
                    self.wait(0.1)
        self._set_market_trade_params(security, amount, limit_price=limit_price)
        self._submit_trade()

        return self._handle_pop_dialogs(
            handler_class=pop_dialog_handler.TradePopDialogHandler,
            security=security,
        )

    def _set_market_trade_type(self, ttype):
        """根据选择的市价交易类型选择对应的下拉选项"""
        selects = self._main.child_window(
            control_id=self._config.TRADE_MARKET_TYPE_CONTROL_ID, class_name="ComboBox"
        )
        for i, text in enumerate(selects.texts()):
            # skip 0 index, because 0 index is current select index
            if i == 0:
                if re.search(ttype, text):  # 当前已经选中
                    return
                else:
                    continue
            if re.search(ttype, text):
                selects.select(i - 1)
                return
        raise TypeError("不支持对应的市价类型: {}".format(ttype))


    @locked_client_operation
    def auto_ipo(self):
        self._switch_left_menus(self._config.AUTO_IPO_MENU_PATH)

        stock_list = self._get_grid_data(self._config.COMMON_GRID_CONTROL_ID)

        if len(stock_list) == 0:
            return {"message": "今日无新股"}
        invalid_list_idx = [
            i for i, v in enumerate(stock_list) if v[self.config.AUTO_IPO_NUMBER] <= 0
        ]

        if len(stock_list) == len(invalid_list_idx):
            return {"message": "没有发现可以申购的新股"}

        self._click(self._config.AUTO_IPO_SELECT_ALL_BUTTON_CONTROL_ID)
        self.wait(0.1)

        for row in invalid_list_idx:
            self._click_grid_by_row(row)
        self.wait(0.1)

        self._click(self._config.AUTO_IPO_BUTTON_CONTROL_ID)
        self.wait(0.1)

        return self._handle_pop_dialogs()

    def _click_grid_by_row(self, row):
        x = self._config.COMMON_GRID_LEFT_MARGIN
        y = (
            self._config.COMMON_GRID_FIRST_ROW_HEIGHT
            + self._config.COMMON_GRID_ROW_HEIGHT * row
        )
        self._app.top_window().child_window(
            control_id=self._config.COMMON_GRID_CONTROL_ID,
            class_name="CVirtualGridCtrl",
        ).click(coords=(x, y))

    @perf_clock
    @locked_client_operation
    def is_exist_pop_dialog(self):
        self.wait(0.5)  # wait dialog display
        try:
            return self._get_pop_dialog() is not None
        except (
            findwindows.ElementNotFoundError,
            timings.TimeoutError,
            RuntimeError,
        ) as ex:
            logger.exception("check pop dialog timeout")
            return False

    @perf_clock
    @locked_client_operation
    def close_pop_dialog(self):
        try:
            dialog = self._get_pop_dialog()
            if dialog is not None:
                dialog.close()
                self.wait(0.2)
        except (
            findwindows.ElementNotFoundError,
            timings.TimeoutError,
            RuntimeError,
        ) as ex:
            pass

    def _run_exe_path(self, exe_path):
        return os.path.join(os.path.dirname(exe_path), "xiadan.exe")

    def _operation_lock_path(self, exe_path):
        return self._run_exe_path(exe_path)

    def wait(self, seconds):
        time.sleep(seconds)

    @locked_client_operation
    def exit(self):
        self._app.kill()

    def _close_prompt_windows(self):
        self.wait(1)
        for window in self._app.windows(class_name="#32770", visible_only=True):
            title = window.window_text()
            if title != self._config.TITLE:
                logging.info("close window %s" % title)
                window.close()
                self.wait(0.2)
        self.wait(1)

    @locked_client_operation
    def close_pormpt_window_no_wait(self):
        for window in self._app.windows(class_name="#32770"):
            if window.window_text() != self._config.TITLE:
                window.close()

    @locked_client_operation
    def trade(self, security, price, amount):
        self._set_trade_params(security, price, amount)

        self._submit_trade()

        return self._handle_pop_dialogs(
            handler_class=pop_dialog_handler.TradePopDialogHandler,
            security=security,
        )

    def _click(self, control_id):
        self._app.top_window().child_window(
            control_id=control_id, class_name="Button"
        ).click()

    @perf_clock
    def _submit_trade(self):
        time.sleep(0.2)
        self._main.child_window(
            control_id=self._config.TRADE_SUBMIT_CONTROL_ID, class_name="Button"
        ).type_keys("{ENTER}")

    @perf_clock
    def __get_top_window_pop_dialog(self):
        return self._app.top_window().window(
            control_id=self._config.POP_DIALOD_TITLE_CONTROL_ID
        )

    @perf_clock
    def _get_pop_dialog(self):
        """返回客户端当前最靠前的可见标准弹窗（#32770 对话框），主窗口自身除外"""
        main_handle = self._main.wrapper_object().handle
        for window in self._app.windows(class_name="#32770", visible_only=True):
            if window.handle != main_handle:
                return window
        return None

    def _get_pop_dialog_title(self, dialog=None):
        dialog = dialog or self._get_pop_dialog()
        if dialog is None:
            raise findwindows.ElementNotFoundError("没有可见弹窗")
        title = next(
            (
                control.window_text()
                for control in dialog.children()
                if control.control_id() == self._config.POP_DIALOD_TITLE_CONTROL_ID
            ),
            None,
        )
        if title is None:
            raise findwindows.ElementNotFoundError("弹窗标题控件不存在")
        return title

    def _set_trade_params(self, security, price, amount):
        self.wait(0.3)
        code = security[-6:]

        self._type_edit_control_keys(self._config.TRADE_SECURITY_CONTROL_ID, code)
        self._handle_market_select_dialog(security)

        self._type_edit_control_keys(
            self._config.TRADE_PRICE_CONTROL_ID,
            easyutils.round_price_by_code(price, code),
        )
        self._type_edit_control_keys(
            self._config.TRADE_AMOUNT_CONTROL_ID, str(int(amount))
        )

    def _set_market_trade_params(self, security, amount, limit_price=None):
        self._type_edit_control_keys(
            self._config.TRADE_AMOUNT_CONTROL_ID, str(int(amount))
        )
        self.wait(0.1)
        price_control = None
        if str(security).startswith("68"):  # 科创板存在限价
            try:
                price_control = self._main.child_window(
                    control_id=self._config.TRADE_PRICE_CONTROL_ID, class_name="Edit"
                )
            except:
                pass
        if price_control is not None:
            price_control.set_edit_text(limit_price)

    def _get_grid_data(self, control_id):
        return self.grid_strategy_instance.get(control_id)

    def _query_history(self, menu_path):
        """
        切换菜单后直接读取 Grid 数据（客户端默认加载数据）
        :param menu_path: 菜单路径列表
        :return: list of dict，已去除空列
        """
        self._switch_left_menus(menu_path)
        data = self._get_grid_data(self._config.COMMON_GRID_CONTROL_ID)
        # 过滤掉 Unnamed 空列
        if data and isinstance(data, list):
            for row in data:
                for key in list(row.keys()):
                    if key.startswith("Unnamed"):
                        del row[key]
        return data


    def _type_edit_control_keys(self, control_id, text):
        if not self._editor_need_type_keys:
            self._main.child_window(
                control_id=control_id, class_name="Edit"
            ).set_edit_text(text)
        else:
            editor = self._main.child_window(control_id=control_id, class_name="Edit")
            self._focus_editor_without_moving_cursor(editor)
            editor.select()
            editor.type_keys("^a{BACKSPACE}", set_foreground=False)
            editor.type_keys(str(text), set_foreground=False, pause=0.05)

    def type_edit_control_keys(self, editor, text):
        if not self._editor_need_type_keys:
            editor.set_edit_text(text)
        else:
            self._focus_editor_without_moving_cursor(editor)
            editor.select()
            editor.type_keys("^a{BACKSPACE}", set_foreground=False)
            editor.type_keys(str(text), set_foreground=False, pause=0.05)

    @staticmethod
    def _focus_editor_without_moving_cursor(editor):
        editor.set_keyboard_focus()

    def _handle_market_select_dialog(self, security):
        """输入证券代码后立即处理可能延迟出现的“请选择证券市场”弹窗"""
        handler = pop_dialog_handler.TradePopDialogHandler(
            self._app, security=security
        )
        code = str(security)[-6:]
        # 已观察到的跨市场冲突场景是深圳 1xxxxx 证券与上海债券代码撞号；
        # 客户端繁忙时该弹窗可能在输入代码一秒后才出现，需要多轮轮询等待。
        attempts = 21 if code.startswith("1") else 7
        for attempt in range(attempts):
            dialog = self._get_pop_dialog()
            if dialog is not None:
                title = self._get_pop_dialog_title(dialog)
                if title == self._config.MARKET_SELECT_DIALOG_TITLE:
                    handler.handle(title, dialog=dialog)
                    self.wait(0.2)
                    return True
                return False
            if attempt < attempts - 1:
                self.wait(0.1)
        return False

    @perf_clock
    def _switch_left_menus(self, path, sleep=0.2):
        self.close_pop_dialog()
        self._get_left_menus_handle().get_item(path).select()
        self._set_foreground()
        self._main.type_keys("{F5}", set_foreground=False)
        self.wait(sleep)

    def _switch_left_menus_by_shortcut(self, shortcut, sleep=0.5):
        self.close_pop_dialog()
        self._set_foreground()
        self._main.type_keys(shortcut)
        self.wait(sleep)

    def _set_foreground(self, window=None):
        """确保主窗口可见且在前台，type_keys 的 verify_actionable 要求窗口可见"""
        window = window or self._main
        if window is None:
            return
        try:
            if window.has_style(win32defines.WS_MINIMIZE):  # 最小化时先还原
                ShowWindow(window.wrapper_object(), 9)  # SW_RESTORE 还原窗口
            else:
                SetForegroundWindow(window.wrapper_object())  # 置前
        except Exception:
            pass

    @functools.lru_cache()
    def _get_left_menus_handle(self):
        count = 2
        while True:
            try:
                handle = self._main.child_window(
                    control_id=129, class_name="SysTreeView32"
                )
                if count <= 0:
                    return handle
                # sometime can't find handle ready, must retry
                handle.wait("ready", 2)
                return handle
            # pylint: disable=broad-except
            except Exception as ex:
                logger.exception("error occurred when trying to get left menus")
            count = count - 1

    def _cancel_entrust_by_double_click(self, row):
        x = self._config.CANCEL_ENTRUST_GRID_LEFT_MARGIN
        y = (
            self._config.CANCEL_ENTRUST_GRID_FIRST_ROW_HEIGHT
            + self._config.CANCEL_ENTRUST_GRID_ROW_HEIGHT * row
        )
        self._app.top_window().child_window(
            control_id=self._config.COMMON_GRID_CONTROL_ID,
            class_name="CVirtualGridCtrl",
        ).double_click(coords=(x, y))

    @locked_client_operation
    def refresh(self):
        self.refresh_strategy.set_trader(self)
        self.refresh_strategy.refresh()

    @perf_clock
    def _handle_pop_dialogs(
        self, handler_class=pop_dialog_handler.PopDialogHandler, security=None
    ):
        if issubclass(handler_class, pop_dialog_handler.TradePopDialogHandler):
            handler = handler_class(self._app, security=security)
        else:
            handler = handler_class(self._app)
        loop_count = 0

        while self.is_exist_pop_dialog():
            loop_count += 1
            logger.info("第 %s 次循环, 检测到弹窗", loop_count)
            dialog = self._get_pop_dialog()
            if dialog is None:
                break
            try:
                title = self._get_pop_dialog_title(dialog)
                logger.info("弹窗标题: '%s'", title)
            except pywinauto.findwindows.ElementNotFoundError as e:
                logger.warning("弹窗存在但无法获取标题, 异常: %s", e)
                return {"message": "success"}

            result = handler.handle(title, dialog=dialog)
            logger.info("handle('%s') 返回: %s", title, result)
            if result:
                return result
        logger.info("弹窗已消失, 共循环 %s 次, 正常退出", loop_count)
        return {"message": "success"}


class BaseLoginClientTrader(ClientTrader):
    @abc.abstractmethod
    def login(self, user, password, exe_path, comm_password=None, **kwargs):
        """Login Client Trader"""
        pass

    def prepare(
        self,
        config_path=None,
        user=None,
        password=None,
        exe_path=None,
        comm_password=None,
        **kwargs
    ):
        """
        登陆客户端
        :param config_path: 登陆配置文件，跟参数登陆方式二选一
        :param user: 账号
        :param password: 明文密码
        :param exe_path: 客户端路径类似 r'C:\\htzqzyb2\\xiadan.exe', 默认 r'C:\\htzqzyb2\\xiadan.exe'
        :param comm_password: 通讯密码
        :return:
        """
        if config_path is not None:
            account = file2dict(config_path)
            user = account["user"]
            password = account["password"]
            comm_password = account.get("comm_password")
            exe_path = account.get("exe_path")
        login_path = exe_path or self._config.DEFAULT_EXE_PATH
        if login_path is None:
            raise ValueError("参数 exe_path 未设置")

        self._client_lock.configure(self._operation_lock_path(login_path))
        with self._client_lock.operation("prepare"):
            self.login(
                user,
                password,
                login_path,
                comm_password,
                **kwargs
            )
            self._init_toolbar()
