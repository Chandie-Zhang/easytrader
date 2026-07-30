# -*- coding: utf-8 -*-


class TradeError(IOError):
    pass


class NotLoginError(Exception):
    def __init__(self, result=None):
        super(NotLoginError, self).__init__()
        self.result = result


class QuotaExceededError(Exception):
    """API 调用配额耗尽"""
    pass


class ClientBusyError(RuntimeError):
    """同一个 GUI 客户端正在被其他线程或进程操作"""
