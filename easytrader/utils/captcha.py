import base64
import io
import json
import logging
import os
import re
import tempfile
import time

import requests
from PIL import Image, ImageFilter

from easytrader import exceptions

logger = logging.getLogger("easytrader")

# -------- Baidu OCR --------
# 在项目根目录放置 baidu_ocr.json：
#   {"api_key": "你的API_Key", "secret_key": "你的Secret_Key"}
# access_token 首次获取后自动写入同一文件，有效期内复用

BAIDU_OCR_CONFIG_FILE = "baidu_ocr.json"

BAIDU_OCR_ENDPOINTS = [
    ("webimage",        "网络图片文字识别",              1000),
    ("general_basic",   "通用文字识别（标准版）",         1000),
    ("general",         "通用文字识别（标准含位置版）",   1000),
    ("accurate_basic",  "通用文字识别（高精度版）",       1000),
    ("accurate",        "通用文字识别（高精度含位置版）", 500),
]


def _load_config():
    """加载 baidu_ocr.json，返回 (api_key, secret_key, access_token, expires_at)"""
    if not os.path.isfile(BAIDU_OCR_CONFIG_FILE):
        raise FileNotFoundError(
            f"找不到配置文件 {BAIDU_OCR_CONFIG_FILE}，"
            f"请在项目根目录（当前目录: {os.getcwd()}）放置该文件，"
            f"格式: {json.dumps({'api_key': 'xxx', 'secret_key': 'xxx'})}"
        )
    with open(BAIDU_OCR_CONFIG_FILE, encoding="utf-8") as f:
        cfg = json.load(f)
    api_key = cfg.get("api_key")
    secret_key = cfg.get("secret_key")
    if not api_key or not secret_key:
        raise ValueError(f"{BAIDU_OCR_CONFIG_FILE} 缺少 api_key 或 secret_key 字段")
    return api_key, secret_key, cfg.get("access_token"), cfg.get("expires_at", 0)


def _save_token(access_token, expires_at):
    """将 access_token 写入 baidu_ocr.json（与 API Key 同文件存储）"""
    with open(BAIDU_OCR_CONFIG_FILE, encoding="utf-8") as f:
        cfg = json.load(f)
    cfg["access_token"] = access_token
    cfg["expires_at"] = expires_at
    with open(BAIDU_OCR_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def _get_access_token():
    """获取或刷新 access_token（优先读文件缓存，过期自动请求新的）"""
    _, _, cached_token, expires_at = _load_config()
    if cached_token and time.time() < expires_at:
        return cached_token

    api_key, secret_key, _, _ = _load_config()
    resp = requests.post(
        "https://aip.baidubce.com/oauth/2.0/token",
        params={"grant_type": "client_credentials", "client_id": api_key, "client_secret": secret_key},
    )
    data = resp.json()
    if "error" in data:
        raise Exception(f"百度 OCR 鉴权失败: {data.get('error_description', data['error'])}")

    access_token = data["access_token"]
    expires_at = time.time() + data.get("expires_in", 2592000) - 3600
    _save_token(access_token, expires_at)
    return access_token


def _recognize_with_baidu(img_path):
    """百度 OCR 识别（5 个接口按优先级轮询，额度耗尽自动切换）"""
    token = _get_access_token()
    with open(img_path, "rb") as f:
        img_base64 = base64.b64encode(f.read()).decode()

    for endpoint, name, _ in BAIDU_OCR_ENDPOINTS:
        try:
            resp = requests.post(
                f"https://aip.baidubce.com/rest/2.0/ocr/v1/{endpoint}?access_token={token}",
                data={"image": img_base64},
            )
            result = resp.json()
            if "words_result" in result:
                text = "".join(item["words"] for item in result["words_result"])
                return "".join(re.findall("[0-9a-zA-Z]", text))
            if result.get("error_code") in (17, 18, 19):
                continue  # 配额耗尽，换下一个接口
        except Exception:
            continue

    raise exceptions.QuotaExceededError(
        "百度 OCR 所有接口配额均已耗尽，"
        "请前往 https://console.bce.baidu.com/ai/#/ai/ocr/overview/index 充值或下月再试"
    )


def _recognize_with_tesseract(img_path):
    """Tesseract 本地识别（需安装 tesseract-ocr + pip install pytesseract）"""
    import pytesseract
    image = Image.open(img_path).convert("L").point(lambda p: 0 if p < 200 else 255)
    result = pytesseract.image_to_string(image)
    return "".join(re.findall("[0-9a-zA-Z]", result))


def captcha_recognize(img_path, backend="auto"):
    """识别验证码图片

    :param backend:
        - 'auto': 百度 OCR → 额度耗尽 → Tesseract
        - 'baidu': 强制使用百度 OCR
        - 'tesseract': 强制使用 Tesseract
    """
    if backend == "tesseract":
        return _recognize_with_tesseract(img_path)

    try:
        return _recognize_with_baidu(img_path)
    except exceptions.QuotaExceededError:
        logger.warning("百度 OCR 额度已耗尽，切换至 Tesseract")
        return _recognize_with_tesseract(img_path)


# -------- 以下为项目原有接口，被其他模块引用 --------

def _image_to_bytes(image, fmt="PNG"):
    buf = io.BytesIO()
    image.save(buf, format=fmt)
    return buf.getvalue()


def recognize_verify_code(image_path, broker="ht"):
    """识别验证码（被 gf/gj/yh_clienttrader 调用）"""
    if broker == "gf":
        return detect_gf_result(image_path)
    if broker in ["yh_client", "gj_client"]:
        return detect_yh_client_result(image_path)
    return captcha_recognize(image_path)


def detect_yh_client_result(image_path):
    api = "http://yh.ez.shidenggui.com:5000/yh_client"
    with open(image_path, "rb") as f:
        rep = requests.post(api, files={"image": f})
    if rep.status_code != 201:
        error = rep.json()["message"]
        raise exceptions.TradeError(f"request {api} error: {error}")
    return rep.json()["result"]


def detect_gf_result(image_path):
    img = Image.open(image_path)
    width, height = img.width if hasattr(img, "width") else img.size
    for x in range(width):
        for y in range(height):
            if img.getpixel((x, y)) < (100, 100, 100):
                img.putpixel((x, y), (256, 256, 256))
    gray = img.convert("L")
    two = gray.point(lambda p: 0 if 68 < p < 90 else 256)
    med = two.filter(ImageFilter.MinFilter).filter(ImageFilter.MedianFilter)
    for _ in range(2):
        med = med.filter(ImageFilter.MedianFilter)
    tmp = tempfile.mktemp(suffix=".png")
    med.save(tmp)
    return captcha_recognize(tmp)
