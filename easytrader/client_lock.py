# -*- coding: utf-8 -*-
import contextlib
import datetime
import functools
import hashlib
import json
import os
import tempfile
import threading

from easytrader import exceptions


MUTATING_OPERATIONS = {
    "auto_ipo",
    "buy",
    "cancel_all_entrusts",
    "cancel_entrust",
    "market_buy",
    "market_sell",
    "market_trade",
    "repo",
    "reverse_repo",
    "sell",
    "trade",
}


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

    def __init__(self, timeout_seconds=30, state_dir=None, mutex_factory=None):
        self._timeout_ms = int(timeout_seconds * 1000)
        self._state_dir = state_dir or tempfile.gettempdir()
        self._mutex_factory = mutex_factory or _Win32Mutex
        self._mutex = None
        self._mutex_name = None
        self._state_path = None
        self._local = threading.local()

    @property
    def configured(self):
        return self._mutex is not None

    @property
    def mutex_name(self):
        return self._mutex_name

    @property
    def state_path(self):
        return self._state_path

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
        self._state_path = os.path.join(
            self._state_dir,
            "easytrader-client-{}.state".format(lock_id),
        )
        self._mutex = self._mutex_factory(mutex_name)

    @contextlib.contextmanager
    def operation(self, operation_name, preserve_state_on_error=False):
        if self._mutex is None:
            raise RuntimeError("客户端操作锁尚未配置，请先连接客户端")

        depth = getattr(self._local, "depth", 0)
        if depth:
            self._local.depth = depth + 1
            try:
                yield
            except BaseException as error:
                if preserve_state_on_error or not isinstance(error, Exception):
                    self._local.keep_state = True
                raise
            finally:
                self._local.depth -= 1
            return

        abandoned = self._mutex.acquire(self._timeout_ms)
        marker_created = False
        try:
            if abandoned:
                if not os.path.exists(self._state_path):
                    self._write_state("abandoned")
                raise exceptions.ClientStateUnknownError(
                    "上一个交易进程异常终止，客户端状态未知"
                )
            if os.path.exists(self._state_path):
                raise exceptions.ClientStateUnknownError(
                    "检测到未完成的客户端操作，请确认委托状态后清除恢复标记"
                )

            self._write_state(operation_name)
            marker_created = True
            self._local.depth = 1
            self._local.keep_state = False
            try:
                yield
            except BaseException as error:
                if preserve_state_on_error or not isinstance(error, Exception):
                    self._local.keep_state = True
                raise
            finally:
                self._local.depth = 0
        finally:
            try:
                keep_state = getattr(self._local, "keep_state", False)
                if marker_created and not keep_state:
                    self._remove_state()
            finally:
                self._local.keep_state = False
                self._mutex.release()

    def clear_recovery_state(self):
        """调用方核对客户端状态后，清除异常退出留下的恢复标记。"""
        if self._mutex is None:
            raise RuntimeError("客户端操作锁尚未配置")

        self._mutex.acquire(self._timeout_ms)
        try:
            self._remove_state()
        finally:
            self._mutex.release()

    def _write_state(self, operation_name):
        state = {
            "operation": operation_name,
            "pid": os.getpid(),
            "thread_id": threading.current_thread().ident,
            "started_at": datetime.datetime.now().isoformat(),
        }
        temp_path = "{}.{}.tmp".format(self._state_path, os.getpid())
        try:
            with open(temp_path, "w", encoding="utf-8") as state_file:
                json.dump(state, state_file, ensure_ascii=False)
            os.replace(temp_path, self._state_path)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def _remove_state(self):
        try:
            os.remove(self._state_path)
        except FileNotFoundError:
            pass


def locked_client_operation(func):
    """在客户端级 Mutex 内执行 ClientTrader 的公开操作。"""

    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        with self._client_lock.operation(
            func.__name__,
            preserve_state_on_error=func.__name__ in MUTATING_OPERATIONS,
        ):
            return func(self, *args, **kwargs)

    return wrapper
