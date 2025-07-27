import json
import os
import threading
import time
import requests
from abc import ABC, abstractmethod
import logging

logging.basicConfig(level=logging.INFO)

# ---------- 抽象接口
class ExchangeRateProvider(ABC):
    @abstractmethod
    def get_rate(self) -> float:
        pass


# ---------- 实际实现：莫斯科交易所
class MoexProvider(ExchangeRateProvider):
    def get_rate(self) -> float:
        url = "https://iss.moex.com/iss/engines/currency/markets/selt/securities/CNYRUB_TOM/candles.json"
        r = requests.get(url, params={"interval": 1, "limit": 1}, timeout=1)
        r.raise_for_status()
        price_rub = float(r.json()["candles"]["data"][0][6])
        return 1 / price_rub


# ---------- 兜底实现：固定值
class FallbackProvider(ExchangeRateProvider):
    def __init__(self, default: float = 0.09):
        self.default = default

    def get_rate(self) -> float:
        return self.default


# ---------- 双缓存服务
class ExchangeRateService:
    _instance = None
    _lock = threading.Lock()
    _fallback_file = os.path.join(os.path.dirname(__file__), "rate_fallback.json")

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._init()
        return cls._instance

    def _init(self):
        self._provider = MoexProvider()
        self._fallback = FallbackProvider()
        self._rate: float = 0.09
        self._last: float = 0
        self._load_fallback()
        self._start_async_refresh()

    # ---------- 持久化兜底
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

    # ---------- 后台定时刷新
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

    # ---------- 对外接口
    def get_exchange_rate(self) -> float:
        return self._rate


# ---------- 全局单例
def get_exchange_rate() -> float:
    return ExchangeRateService().get_exchange_rate()