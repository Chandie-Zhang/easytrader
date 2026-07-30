# -*- coding: utf-8 -*-
import contextlib
import functools
import hashlib
import os
import threading

from easytrader import exceptions
from easytrader.log import logger


class _Win32Mutex:
    """Windows 命名 Mutex 封装，延迟导入 pywin32 便于单元测试。"""

    def __init__(self, name):
        import win32api
        import win32event

        self._win32api = win32api
        self._win32event = win32event
        self._handle = win32event.CreateMutex(None, False, name)

    def acquire(self, timeout_ms):
        result = self._win32event.WaitForSingleObject(self._handle, timeout_ms)
        if result == self._win32event.WAIT_OBJECT_0:
            return False
        if result == self._win32event.WAIT_ABANDONED:
            return True
        if result == self._win32event.WAIT_TIMEOUT:
            raise exceptions.ClientBusyError("同花顺客户端正被其他进程操作")
        raise RuntimeError("等待同花顺客户端进程锁失败: {}".format(result))

    def release(self):
        self._win32event.ReleaseMutex(self._handle)

    def close(self):
        self._win32api.CloseHandle(self._handle)


class ClientOperationLock:
    """串行执行所有指向同一个 GUI 客户端的操作。"""

    def __init__(self, timeout_seconds=30, mutex_factory=None):
        self._timeout_ms = int(timeout_seconds * 1000)
        self._mutex_factory = mutex_factory or _Win32Mutex
        self._mutex = None
        self._mutex_name = None
        self._local = threading.local()

    @property
    def configured(self):
        return self._mutex is not None

    @property
    def mutex_name(self):
        return self._mutex_name

    def configure(self, client_path):
        normalized_path = os.path.normcase(
            os.path.realpath(os.path.abspath(client_path))
        )
        lock_id = hashlib.sha256(
            normalized_path.encode("utf-8")
        ).hexdigest()[:24]
        mutex_name = r"Local\easytrader-client-{}".format(lock_id)

        if self._mutex_name == mutex_name:
            return
        if self._mutex is not None:
            raise RuntimeError("客户端操作锁已绑定，不能切换到其他客户端")

        self._mutex_name = mutex_name
        self._mutex = self._mutex_factory(mutex_name)

    @contextlib.contextmanager
    def operation(self, operation_name):
        if self._mutex is None:
            raise RuntimeError("客户端操作锁尚未配置，请先连接客户端")

        depth = getattr(self._local, "depth", 0)
        if depth:
            self._local.depth = depth + 1
            try:
                yield
            finally:
                self._local.depth -= 1
            return

        abandoned = self._mutex.acquire(self._timeout_ms)
        if abandoned:
            logger.warning(
                "检测到持锁进程异常退出，已自动接管客户端操作锁: %s",
                operation_name,
            )
        try:
            self._local.depth = 1
            try:
                yield
            finally:
                self._local.depth = 0
        finally:
            self._mutex.release()


def locked_client_operation(func):
    """在客户端级 Mutex 内执行 ClientTrader 的公开操作。"""

    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        with self._client_lock.operation(func.__name__):
            return func(self, *args, **kwargs)

    return wrapper
