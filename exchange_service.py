import json
import logging
import os
import requests
import threading
import time
from abc import ABC, abstractmethod


logging.basicConfig(level=logging.INFO)


# ---------- 抽象接口
class ExchangeRateProvider(ABC):
    @abstractmethod
    def get_rate(self) -> float:
        pass


# ---------- 中国银行官网实时抓取
class BocProvider(ExchangeRateProvider):
    """
    使用 exchangerate-api.com 免费接口
    直接返回 1 RUB → CNY 的实时汇率
    """
    def __init__(self):
        self.url = "https://api.exchangerate-api.com/v4/latest/RUB"

    def get_rate(self) -> float:
        try:
            r = requests.get(self.url, timeout=10)
            r.raise_for_status()
            data = r.json()
            # rates.CNY 即 1 RUB 兑多少 CNY
            return float(data["rates"]["CNY"])
        except requests.RequestException as e:
            logging.warning("第三方汇率接口失败: %s", e)
        raise ValueError("第三方接口未返回卢布汇率")


# ---------- 兜底实现：固定值
class FallbackProvider(ExchangeRateProvider):
    def __init__(self, default: float = 9.02):
        self.default = default

    def get_rate(self) -> float:
        return self.default


# ---------- 双缓存服务（单例）
class ExchangeRateService:
    _instance = None
    _lock = threading.Lock()
    _fallback_file = os.path.join(
        os.path.dirname(__file__),
        "rate_fallback.json"
    )

    def __init__(self):
        # 仅为静态类型检查器提供属性初始化，避免"实例特性在 __init__ 外部定义"
        if not hasattr(self, "_rate"):
            self._provider = BocProvider()
            self._fallback = FallbackProvider()
            self._rate = 9.02
            self._last = 0.0
            self._refresher_started = False

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._init()
        return cls._instance

    def _init(self):
        self._provider = BocProvider()
        self._fallback = FallbackProvider()
        self._rate: float = 9.02
        self._last: float = 0
        self._load_fallback()
        self._start_async_refresh()

    @classmethod
    def _reset_for_testing(cls):
        """重置单例实例，仅用于测试"""
        with cls._lock:
            cls._instance = None

    def _reset_cache_for_testing(self):
        """重置缓存，仅用于测试"""
        self._last = 0.0
        self._rate = 9.02  # 重置为默认值

    def _load_fallback(self):
        try:
            with open(self._fallback_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._rate = data["rate"]
            self._last = data["ts"]
            logging.info("兜底汇率已加载: %.5f", self._rate)
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            self._rate = self._fallback.get_rate()
            self._last = time.time()
            logging.warning("兜底文件缺失，使用默认值: %.5f", self._rate)

    def _save_fallback(self, rate: float):
        try:
            with open(self._fallback_file, "w", encoding="utf-8") as f:
                json.dump({"rate": rate, "ts": time.time()}, f)
        except OSError:
            logging.exception("无法保存兜底汇率")

    def _start_async_refresh(self):
        if not getattr(self, "_refresher_started", False):
            threading.Thread(target=self._async_refresh, daemon=True).start()
            self._refresher_started = True

    def _async_refresh(self):
        while True:
            try:
                new_rate = self._provider.get_rate()
                self._rate = new_rate
                self._last = time.time()
                self._save_fallback(new_rate)
                logging.info("异步刷新汇率: %.5f", new_rate)
            except (requests.RequestException, ValueError):
                logging.exception("异步获取汇率失败，继续使用旧值")
            time.sleep(3600)  # 60 分钟

    def get_exchange_rate(self) -> float:
        # 检查是否需要刷新（避免每次都发起网络请求）
        current_time = time.time()
        # 如果距离上次刷新不到60分钟，直接返回缓存值
        if current_time - self._last < 3600:  # 60分钟缓存
            return self._rate

        # 尝试即时刷新（测试可通过mock requests.get 控制返回）
        try:
            new_rate = self._provider.get_rate()
            self._rate = new_rate
            self._last = current_time
            self._save_fallback(new_rate)
        except (requests.RequestException, ValueError):
            pass
        return self._rate


# ---------- 美元汇率提供者
class UsdProvider(ExchangeRateProvider):
    """
    使用 exchangerate-api.com 免费接口
    获取 1 USD → CNY 的实时汇率
    """
    def __init__(self):
        self.url = "https://api.exchangerate-api.com/v4/latest/USD"

    def get_rate(self) -> float:
        try:
            r = requests.get(self.url, timeout=10)
            r.raise_for_status()
            data = r.json()
            # rates.CNY 即 1 USD 兑多少 CNY
            return float(data["rates"]["CNY"])
        except requests.RequestException as e:
            logging.warning("美元汇率接口失败: %s", e)
        raise ValueError("第三方接口未返回美元汇率")


# ---------- 美元汇率服务
class UsdExchangeRateService:
    _instance = None
    _lock = threading.Lock()
    _fallback_file = os.path.join(
        os.path.dirname(__file__),
        "usd_rate_fallback.json"
    )

    def __init__(self):
        # 仅为静态类型检查器提供属性初始化，避免"实例特性在 __init__ 外部定义"
        if not hasattr(self, "_rate"):
            self._provider = UsdProvider()
            self._fallback = FallbackProvider(default=7.2)
            self._rate = 7.2
            self._last = 0.0
            self._refresher_started = False

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._init()
        return cls._instance

    def _init(self):
        self._provider = UsdProvider()
        self._fallback = FallbackProvider(default=7.2)  # 美元默认汇率
        self._rate: float = 7.2
        self._last: float = 0
        self._load_fallback()
        self._start_async_refresh()

    @classmethod
    def _reset_for_testing(cls):
        """重置单例实例，仅用于测试"""
        with cls._lock:
            cls._instance = None

    def _reset_cache_for_testing(self):
        """重置缓存，仅用于测试"""
        self._last = 0.0
        self._rate = 7.2  # 重置为默认值

    def _load_fallback(self):
        try:
            with open(self._fallback_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._rate = data["rate"]
            self._last = data["ts"]
            logging.info("美元兜底汇率已加载: %.5f", self._rate)
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            self._rate = self._fallback.get_rate()
            self._last = time.time()
            logging.warning("美元兜底文件缺失，使用默认值: %.5f", self._rate)

    def _save_fallback(self, rate: float):
        try:
            with open(self._fallback_file, "w", encoding="utf-8") as f:
                json.dump({"rate": rate, "ts": time.time()}, f)
        except OSError:
            logging.exception("无法保存美元兜底汇率")

    def _start_async_refresh(self):
        if not getattr(self, "_refresher_started", False):
            threading.Thread(target=self._async_refresh, daemon=True).start()
            self._refresher_started = True

    def _async_refresh(self):
        while True:
            try:
                new_rate = self._provider.get_rate()
                self._rate = new_rate
                self._last = time.time()
                self._save_fallback(new_rate)
                logging.info("异步刷新美元汇率: %.5f", new_rate)
            except (requests.RequestException, ValueError):
                logging.exception("异步获取美元汇率失败，继续使用旧值")
            time.sleep(3600)  # 60 分钟

    def get_exchange_rate(self) -> float:
        # 检查是否需要刷新（避免每次都发起网络请求）
        current_time = time.time()
        # 如果距离上次刷新不到60分钟，直接返回缓存值
        if current_time - self._last < 3600:  # 60分钟缓存
            return self._rate

        try:
            new_rate = self._provider.get_rate()
            self._rate = new_rate
            self._last = current_time
            self._save_fallback(new_rate)
        except (requests.RequestException, ValueError):
            pass
        return self._rate


# ---------- 全局单例
def get_exchange_rate() -> float:
    return ExchangeRateService().get_exchange_rate()


def get_usd_rate() -> float:
    """获取美元兑人民币汇率"""
    return UsdExchangeRateService().get_exchange_rate()
