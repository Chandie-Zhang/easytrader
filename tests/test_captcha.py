# coding: utf-8
import unittest
from unittest.mock import patch

from easytrader.utils.captcha import captcha_recognize


class TestCaptchaRecognizeFallback(unittest.TestCase):
    @patch("easytrader.utils.captcha._recognize_with_tesseract", return_value="1234")
    @patch("easytrader.utils.captcha._recognize_with_baidu")
    def test_auto_falls_back_to_tesseract_on_any_baidu_failure(
        self, mock_baidu, mock_tess
    ):
        # 未配置 baidu_ocr.json（FileNotFoundError）等任何百度失败，
        # auto 模式应降级到 Tesseract 而非抛出
        mock_baidu.side_effect = FileNotFoundError("找不到配置文件 baidu_ocr.json")

        result = captcha_recognize("img.png", backend="auto")

        self.assertEqual(result, "1234")
        mock_tess.assert_called_once_with("img.png")

    @patch("easytrader.utils.captcha._recognize_with_tesseract", return_value="abcd")
    @patch("easytrader.utils.captcha._recognize_with_baidu")
    def test_baidu_forced_raises_without_fallback(self, mock_baidu, mock_tess):
        # 强制 baidu 模式失败应直接抛出，不降级
        mock_baidu.side_effect = RuntimeError("网络异常")

        with self.assertRaises(RuntimeError):
            captcha_recognize("img.png", backend="baidu")

        mock_tess.assert_not_called()

    @patch("easytrader.utils.captcha._recognize_with_tesseract", return_value="9999")
    def test_tesseract_forced_direct(self, mock_tess):
        result = captcha_recognize("img.png", backend="tesseract")
        self.assertEqual(result, "9999")
        mock_tess.assert_called_once_with("img.png")


if __name__ == "__main__":
    unittest.main()
