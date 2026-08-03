# coding: utf-8
import unittest
from unittest.mock import MagicMock, patch

from easytrader.grid_strategies import Copy


class TestCopyCaptchaFallback(unittest.TestCase):
    def setUp(self):
        self.trader = MagicMock()
        # 模拟验证码弹窗存在
        captcha_window = MagicMock()
        captcha_window.exists.return_value = True
        self.trader.app.top_window.return_value = MagicMock()
        self.trader.app.top_window.return_value.window.return_value = captcha_window

        self.copy = Copy()
        self.copy.set_trader(self.trader)
        Copy._need_captcha_reg = True

    def tearDown(self):
        Copy._need_captcha_reg = True

    @patch("easytrader.grid_strategies.pywinauto.clipboard.GetData", return_value="持仓数据")
    @patch("easytrader.grid_strategies.captcha_recognize")
    def test_recognize_failure_falls_back_to_clipboard(self, mock_recognize, mock_getdata):
        # 未配置 baidu_ocr.json 时 captcha_recognize 抛 FileNotFoundError，
        # 不应崩溃，应输出 warning 后继续读取剪贴板
        mock_recognize.side_effect = FileNotFoundError("找不到配置文件 baidu_ocr.json")

        result = self.copy._get_clipboard_data()

        self.assertEqual(result, "持仓数据")
        mock_getdata.assert_called()
        # 识别失败后不应尝试输入验证码
        self.trader.type_edit_control_keys.assert_not_called()

    @patch("easytrader.grid_strategies.pywinauto.clipboard.GetData", side_effect=[Exception("empty"), "data"])
    @patch("easytrader.grid_strategies.captcha_recognize", side_effect=RuntimeError("网络异常"))
    def test_recognize_network_error_also_falls_back(self, mock_recognize, mock_getdata):
        # 网络异常等其它错误同样兜底，不崩溃
        result = self.copy._get_clipboard_data()
        self.assertEqual(result, "data")


if __name__ == "__main__":
    unittest.main()
