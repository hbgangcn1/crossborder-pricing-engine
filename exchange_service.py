import json
import logging
import os
import requests
import threading
import time
from abc import ABC, abstractmethod
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from typing import Any, cast


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
        self.session = requests.Session()
        retry = Retry(total=2, backoff_factor=0.5,
                      status_forcelist=[500, 502, 503, 504],
                      allowed_methods=frozenset(['GET']))
        adapter = HTTPAdapter(max_retries=cast(Any, retry))
        self.session.mount("https://", adapter)
        self.session.headers.update({"User-Agent": "Mozilla/5.0"})

    def get_rate(self) -> float:
        try:
            r = self.session.get(self.url, timeout=10)
            r.raise_for_status()
            data = r.json()
            # rates.CNY 即 1 RUB 兑多少 CNY
            return float(data["rates"]["CNY"])
        except Exception as e:
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
            except requests.RequestException:
                logging.exception("异步获取汇率失败，继续使用旧值")
            time.sleep(1800)  # 30 分钟

    def get_exchange_rate(self) -> float:
        return self._rate


# ---------- 美元汇率提供者
class UsdProvider(ExchangeRateProvider):
    """
    使用 exchangerate-api.com 免费接口
    获取 1 USD → CNY 的实时汇率
    """
    def __init__(self):
        self.url = "https://api.exchangerate-api.com/v4/latest/USD"
        self.session = requests.Session()
        retry = Retry(total=2, backoff_factor=0.5,
                      status_forcelist=[500, 502, 503, 504],
                      allowed_methods=frozenset(['GET']))
        adapter = HTTPAdapter(max_retries=cast(Any, retry))
        self.session.mount("https://", adapter)
        self.session.headers.update({"User-Agent": "Mozilla/5.0"})

    def get_rate(self) -> float:
        try:
            r = self.session.get(self.url, timeout=10)
            r.raise_for_status()
            data = r.json()
            # rates.CNY 即 1 USD 兑多少 CNY
            return float(data["rates"]["CNY"])
        except Exception as e:
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
            except requests.RequestException:
                logging.exception("异步获取美元汇率失败，继续使用旧值")
            time.sleep(1800)  # 30 分钟

    def get_exchange_rate(self) -> float:
        return self._rate


# ---------- 全局单例
def get_exchange_rate() -> float:
    return ExchangeRateService().get_exchange_rate()


def get_usd_rate() -> float:
    """获取美元兑人民币汇率"""
    return UsdExchangeRateService().get_exchange_rate()
