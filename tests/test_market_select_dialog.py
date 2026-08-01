# coding: utf-8
import unittest
from unittest.mock import MagicMock, call

from easytrader import exceptions
from easytrader.clienttrader import ClientTrader
from easytrader.pop_dialog_handler import PopDialogHandler, TradePopDialogHandler
from easytrader.utils.market import MARKET_SH, MARKET_SZ, get_security_market
from easytrader.utils.win_gui import win32defines


def make_control(control_id, text=""):
    control = MagicMock()
    control.control_id.return_value = control_id
    control.window_text.return_value = text
    return control


class _NoControlsDialog:
    """模拟没有 Static/Edit/RichEdit 子控件的弹窗（如非交易日"提交失败"提示）"""

    def __init__(self):
        self.confirm = MagicMock()

    def __getattr__(self, name):
        # 模拟 pywinauto：访问不存在的子控件属性抛 AttributeError
        raise AttributeError(
            "'DialogWrapper' object has no attribute '{}'".format(name)
        )

    def __getitem__(self, key):
        return self.confirm


class TestSecurityMarket(unittest.TestCase):
    def test_uses_existing_prefix_rules(self):
        self.assertEqual(get_security_market("160140"), MARKET_SZ)
        self.assertEqual(get_security_market("501025"), MARKET_SH)
        self.assertEqual(get_security_market("600000"), MARKET_SH)
        self.assertEqual(get_security_market("000001"), MARKET_SZ)

    def test_explicit_prefix_overrides_ambiguous_code(self):
        self.assertEqual(get_security_market("sh160140"), MARKET_SH)
        self.assertEqual(get_security_market("sz160140"), MARKET_SZ)

    def test_rejects_unsupported_or_invalid_codes(self):
        self.assertIsNone(get_security_market("bj430047"))
        self.assertIsNone(get_security_market("abc"))
        self.assertIsNone(get_security_market("12345"))


class TestMarketSelectDialogHandler(unittest.TestCase):
    def test_unchecks_remember_and_selects_shenzhen_with_bm_click(self):
        remember = make_control(1504)
        remember.get_check_state.return_value = 1
        sh_button = make_control(1997, "上海Ａ股\n(19兵团06)")
        sz_button = make_control(1967, "深圳Ａ股\n(美国REIT精选LOF)")
        dialog = MagicMock()
        dialog.children.return_value = [sh_button, sz_button, remember]

        handler = TradePopDialogHandler(MagicMock(), security="160140")
        result = handler.handle("请选择证券市场", dialog=dialog)

        self.assertIsNone(result)
        remember.send_message.assert_called_once_with(win32defines.BM_CLICK)
        sz_button.send_message.assert_called_once_with(win32defines.BM_CLICK)
        sh_button.send_message.assert_not_called()

    def test_selects_explicit_shanghai_market(self):
        remember = make_control(1504)
        remember.get_check_state.return_value = 0
        sh_button = make_control(1997)
        sz_button = make_control(1967)
        dialog = MagicMock()
        dialog.children.return_value = [remember, sh_button, sz_button]

        handler = TradePopDialogHandler(MagicMock(), security="sh160140")
        handler.handle("请选择证券市场", dialog=dialog)

        remember.send_message.assert_not_called()
        sh_button.send_message.assert_called_once_with(win32defines.BM_CLICK)
        sz_button.send_message.assert_not_called()


class TestClientTraderDialogFlow(unittest.TestCase):
    def setUp(self):
        self.trader = ClientTrader()
        self.trader._app = MagicMock()
        self.trader._main = MagicMock()
        self.trader.wait = MagicMock()

    def test_pop_dialog_detection_only_uses_visible_standard_dialogs(self):
        self.trader._main.wrapper_object.return_value.handle = 10
        dialog = MagicMock()
        dialog.handle = 20
        self.trader._app.windows.return_value = [dialog]

        self.assertIs(self.trader._get_pop_dialog(), dialog)
        self.trader._app.windows.assert_called_once_with(
            class_name="#32770", visible_only=True
        )

    def test_main_window_is_not_treated_as_dialog(self):
        self.trader._main.wrapper_object.return_value.handle = 10
        main = MagicMock()
        main.handle = 10
        self.trader._app.windows.return_value = [main]

        self.assertIsNone(self.trader._get_pop_dialog())

    def test_type_keys_clears_existing_text_without_forcing_foreground(self):
        editor = MagicMock()
        self.trader._main.child_window.return_value = editor
        self.trader.enable_type_keys_for_editor()

        self.trader._type_edit_control_keys(1032, "160140")

        editor.set_keyboard_focus.assert_called_once_with()
        editor.select.assert_called_once_with()
        self.assertEqual(
            editor.type_keys.call_args_list,
            [
                call("^a{BACKSPACE}", set_foreground=False),
                call("160140", set_foreground=False, pause=0.05),
            ],
        )

    def test_focus_retries_when_editor_disabled_then_succeeds(self):
        # 客户端页面切换（如市价委托页切回卖出页）时控件短暂 disabled，
        # _focus_editor_without_moving_cursor 应轮询重试而非直接崩溃
        editor = MagicMock()
        editor.is_enabled.side_effect = [False, False, True]
        self.trader.wait = MagicMock()

        self.trader._focus_editor_without_moving_cursor(editor)

        editor.set_keyboard_focus.assert_called_once_with()
        self.assertEqual(self.trader.wait.call_count, 2)

    def test_focus_raises_trade_error_when_editor_never_enabled(self):
        # 控件始终 disabled（如非交易时段/市价委托页）时，超时后抛明确
        # TradeError，而不是 pywintypes.error(87) 裸崩溃
        editor = MagicMock()
        editor.is_enabled.return_value = False
        self.trader.wait = MagicMock()

        with self.assertRaises(exceptions.TradeError):
            self.trader._focus_editor_without_moving_cursor(editor)

        editor.set_keyboard_focus.assert_not_called()
        self.assertEqual(self.trader.wait.call_count, 9)

    def test_extract_content_returns_empty_when_dialog_has_no_static(self):
        # 非交易日"提交失败：Begin failed!"提示弹窗没有 Static 子控件，
        # 旧的 dialog.Static 属性访问会抛 AttributeError，现在应安全返回空串
        dialog = _NoControlsDialog()
        self.trader._app.top_window.return_value = dialog
        handler = PopDialogHandler(self.trader._app)
        self.assertEqual(handler._extract_content(), "")

    def test_trade_prompt_dialog_without_static_auto_closes(self):
        # "提示"弹窗无文本内容时（如非交易日提交失败），点击确定自动关闭，
        # 不抛 AttributeError / TradeError，让交易流程正常结束
        dialog = _NoControlsDialog()
        handler = TradePopDialogHandler(self.trader._app, security="160140")
        result = handler.handle("提示", dialog=dialog)
        self.assertIsNone(result)
        dialog.confirm.click.assert_called_once_with()

    def test_trade_prompt_dialog_with_real_error_still_raises(self):
        # 能读到真实失败内容（如"资金不足"）时仍应抛 TradeError，便于上层感知
        dialog = MagicMock()
        dialog.Static.window_text.return_value = "资金不足"
        handler = TradePopDialogHandler(self.trader._app, security="160140")
        with self.assertRaises(exceptions.TradeError):
            handler.handle("提示", dialog=dialog)
        dialog["确定"].click.assert_called_once_with()

    def test_trade_success_prompt_returns_entrust_no(self):
        dialog = MagicMock()
        dialog.Static.window_text.return_value = "委托成功，编号 123456"
        handler = TradePopDialogHandler(self.trader._app, security="160140")
        result = handler.handle("提示", dialog=dialog)
        self.assertEqual(result, {"entrust_no": "123456"})
        dialog["确定"].click.assert_called_once_with()

    def test_waits_for_delayed_market_dialog_and_handles_it(self):
        sz_button = make_control(1967)
        dialog = MagicMock()
        dialog.children.return_value = [sz_button]
        self.trader._get_pop_dialog = MagicMock(
            side_effect=[None, None, None, None, dialog]
        )
        self.trader._get_pop_dialog_title = MagicMock(
            return_value="请选择证券市场"
        )

        handled = self.trader._handle_market_select_dialog("160140")

        self.assertTrue(handled)
        self.assertEqual(self.trader.wait.call_args_list, [call(0.1)] * 4 + [call(0.2)])
        self.trader._get_pop_dialog_title.assert_called_once_with(dialog)
        sz_button.send_message.assert_called_once_with(win32defines.BM_CLICK)

    def test_limit_trade_handles_market_before_price_and_amount(self):
        events = []
        self.trader._type_edit_control_keys = MagicMock(
            side_effect=lambda control_id, text: events.append((control_id, str(text)))
        )
        self.trader._handle_market_select_dialog = MagicMock(
            side_effect=lambda security: events.append(("market", security))
        )

        self.trader._set_trade_params("160140", 1.494, 100)

        self.assertEqual(events[0], (1032, "160140"))
        self.assertEqual(events[1], ("market", "160140"))
        self.assertEqual(events[2][0], 1033)
        self.assertEqual(events[3], (1034, "100"))


if __name__ == "__main__":
    unittest.main()
