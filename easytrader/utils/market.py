# coding: utf-8
"""客户端弹窗中 A 股市场选择相关的辅助函数。"""

from easytrader.utils.stock import get_stock_type


MARKET_SH = "上海Ａ股"
MARKET_SZ = "深圳Ａ股"


def get_security_market(security):
    """返回六位证券代码对应的客户端市场名称（上海Ａ股 / 深圳Ａ股），无法判断时返回 None。"""
    value = str(security).strip().lower()
    code = value[-6:]
    if len(code) != 6 or not code.isdigit():
        return None

    if value.startswith("sh"):
        stock_type = "sh"
    elif value.startswith("sz"):
        stock_type = "sz"
    else:
        stock_type = get_stock_type(code)

    if stock_type == "sh":
        return MARKET_SH
    if stock_type == "sz":
        return MARKET_SZ
    return None
