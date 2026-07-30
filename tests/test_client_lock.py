# coding: utf-8
import importlib.util
import multiprocessing
import os
import tempfile
import threading
import time
import unittest

from easytrader import exceptions
from easytrader.client_lock import ClientOperationLock


class ThreadMutex:
    _locks = {}
    _registry_lock = threading.Lock()

    def __init__(self, name):
        with self._registry_lock:
            self._lock = self._locks.setdefault(name, threading.Lock())
        self.acquire_count = 0
        self.release_count = 0
        self.abandoned = False

    def acquire(self, timeout_ms):
        acquired = self._lock.acquire(timeout=timeout_ms / 1000)
        if not acquired:
            raise exceptions.ClientBusyError("busy")
        self.acquire_count += 1
        return self.abandoned

    def release(self):
        self.release_count += 1
        self._lock.release()


class MutexFactory:
    def __init__(self):
        self.instances = []

    def __call__(self, name):
        mutex = ThreadMutex(name)
        self.instances.append(mutex)
        return mutex


def process_lock_worker(client_path, events, worker_name, hold_seconds):
    lock = ClientOperationLock(timeout_seconds=5)
    lock.configure(client_path)
    with lock.operation("worker"):
        events.put(("{}-enter".format(worker_name), time.time()))
        time.sleep(hold_seconds)
        events.put(("{}-exit".format(worker_name), time.time()))


def crashing_process_worker(client_path, entered):
    lock = ClientOperationLock(timeout_seconds=5)
    lock.configure(client_path)
    with lock.operation("crash"):
        entered.set()
        os._exit(0)


class TestClientOperationLock(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.client_path = os.path.join(self.temp_dir.name, "xiadan.exe")
        self.factory = MutexFactory()

    def tearDown(self):
        self.temp_dir.cleanup()

    def make_lock(self, timeout_seconds=1):
        lock = ClientOperationLock(
            timeout_seconds=timeout_seconds,
            mutex_factory=self.factory,
        )
        lock.configure(self.client_path)
        return lock

    def test_same_client_path_uses_same_mutex_name(self):
        first = self.make_lock()
        second = self.make_lock()

        self.assertEqual(first.mutex_name, second.mutex_name)

    def test_operation_releases_mutex_after_exception(self):
        lock = self.make_lock()
        mutex = self.factory.instances[-1]

        with self.assertRaises(ValueError):
            with lock.operation("buy"):
                raise ValueError("failed")

        self.assertEqual(mutex.acquire_count, 1)
        self.assertEqual(mutex.release_count, 1)

    def test_keyboard_interrupt_releases_mutex(self):
        lock = self.make_lock()
        mutex = self.factory.instances[-1]

        with self.assertRaises(KeyboardInterrupt):
            with lock.operation("position"):
                raise KeyboardInterrupt()

        self.assertEqual(mutex.release_count, 1)

    def test_nested_operation_only_acquires_mutex_once(self):
        lock = self.make_lock()
        mutex = self.factory.instances[-1]

        with lock.operation("outer"):
            with lock.operation("inner"):
                pass

        self.assertEqual(mutex.acquire_count, 1)
        self.assertEqual(mutex.release_count, 1)

    def test_abandoned_mutex_is_acquired_automatically(self):
        lock = self.make_lock()
        mutex = self.factory.instances[-1]
        mutex.abandoned = True
        entered = False

        with lock.operation("buy"):
            entered = True

        self.assertTrue(entered)
        self.assertEqual(mutex.release_count, 1)

    def test_timeout_does_not_enter_operation(self):
        first = self.make_lock()
        second = self.make_lock(timeout_seconds=0.01)

        with first.operation("first"):
            with self.assertRaises(exceptions.ClientBusyError):
                with second.operation("second"):
                    pass

    def test_two_threads_do_not_interleave(self):
        first = self.make_lock()
        second = self.make_lock()
        first_entered = threading.Event()
        allow_first_exit = threading.Event()
        events = []

        def first_worker():
            with first.operation("first"):
                events.append("first-enter")
                first_entered.set()
                allow_first_exit.wait(2)
                events.append("first-exit")

        def second_worker():
            first_entered.wait(2)
            with second.operation("second"):
                events.append("second-enter")

        first_thread = threading.Thread(target=first_worker)
        second_thread = threading.Thread(target=second_worker)
        first_thread.start()
        second_thread.start()
        first_entered.wait(2)
        time.sleep(0.05)
        self.assertEqual(events, ["first-enter"])
        allow_first_exit.set()
        first_thread.join(2)
        second_thread.join(2)

        self.assertEqual(
            events,
            ["first-enter", "first-exit", "second-enter"],
        )


@unittest.skipUnless(
    importlib.util.find_spec("win32event") is not None,
    "需要安装 pywin32",
)
class TestWindowsProcessLock(unittest.TestCase):
    def test_independent_processes_are_serialized(self):
        with tempfile.TemporaryDirectory() as state_dir:
            client_path = os.path.join(state_dir, "xiadan.exe")
            events = multiprocessing.Queue()
            first = multiprocessing.Process(
                target=process_lock_worker,
                args=(client_path, events, "first", 0.3),
            )
            second = multiprocessing.Process(
                target=process_lock_worker,
                args=(client_path, events, "second", 0),
            )

            first.start()
            first_enter = events.get(timeout=3)
            second.start()
            remaining = [events.get(timeout=3), events.get(timeout=3)]
            first.join(3)
            second.join(3)

            by_name = {event[0]: event[1] for event in remaining}
            self.assertEqual(first_enter[0], "first-enter")
            self.assertIn("first-exit", by_name)
            self.assertIn("second-enter", by_name)
            self.assertGreaterEqual(
                by_name["second-enter"],
                by_name["first-exit"],
            )

    def test_lock_is_acquired_after_process_crash(self):
        with tempfile.TemporaryDirectory() as state_dir:
            client_path = os.path.join(state_dir, "xiadan.exe")
            entered = multiprocessing.Event()
            lock = ClientOperationLock(timeout_seconds=3)
            lock.configure(client_path)
            process = multiprocessing.Process(
                target=crashing_process_worker,
                args=(client_path, entered),
            )
            process.start()
            self.assertTrue(entered.wait(3))
            process.join(3)

            acquired = False
            with lock.operation("next"):
                acquired = True
            self.assertTrue(acquired)
