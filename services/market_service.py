"""
services/market_service.py
Adaptador de Binance y cálculo de indicadores técnicos para CryptoAdvisor.

Implementa lo pedido por el informe:
- Datos OHLCV desde Binance API pública.
- Ticker 24h y profundidad básica de mercado.
- Indicadores en backend: RSI(14), MACD, Bollinger, EMA-20, SMA-50, VWAP.
- Regla RN-01: volumen 24h mínimo de 500,000 USDT.
- Caché simple de 60 segundos para reducir llamadas a Binance.
"""

from __future__ import annotations

import json
import math
import os
import time
import urllib.parse
import urllib.request
from statistics import mean, pstdev
from typing import Any

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "settings.json")
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    CONFIG = json.load(f)

BASE_URL = CONFIG.get("binance", {}).get("base_url", "https://api.binance.com/api/v3")
INTERVAL = CONFIG.get("binance", {}).get("interval", "1h")
LIMIT = int(CONFIG.get("binance", {}).get("limit", 120))
CACHE_TTL_SECONDS = int(CONFIG.get("binance", {}).get("cache_ttl_seconds", 60))

LIQUIDEZ_MINIMA_USDT = 500_000.0
REQUEST_TIMEOUT = 10
_cache: dict[str, tuple[float, Any]] = {}


class BinanceError(RuntimeError):
    """Error controlado de conexión, formato o respuesta de Binance."""


def _cache_get(key: str):
    item = _cache.get(key)
    if not item:
        return None
    ts, value = item
    if (time.time() - ts) <= CACHE_TTL_SECONDS:
        return value
    _cache.pop(key, None)
    return None


def _cache_set(key: str, value):
    _cache[key] = (time.time(), value)


def _request_json(endpoint: str, params: dict | None = None):
    params = params or {}
    query = urllib.parse.urlencode(params)
    url = f"{BASE_URL}{endpoint}"
    if query:
        url = f"{url}?{query}"

    cached = _cache_get(url)
    if cached is not None:
        return cached

    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "CryptoAdvisor/1.0"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            raw = resp.read().decode("utf-8")
            data = json.loads(raw)
            _cache_set(url, data)
            return data
    except Exception as exc:
        raise BinanceError(f"No se pudo consultar Binance: {exc}") from exc


def obtener_precio_actual(symbol: str) -> float:
    data = _request_json("/ticker/price", {"symbol": symbol.upper()})
    return float(data["price"])


def obtener_ticker_24h(symbol: str) -> dict:
    data = _request_json("/ticker/24hr", {"symbol": symbol.upper()})
    return {
        "symbol": data.get("symbol", symbol.upper()),
        "lastPrice": float(data.get("lastPrice", 0)),
        "priceChangePercent": float(data.get("priceChangePercent", 0)),
        "quoteVolume": float(data.get("quoteVolume", 0)),
        "volume": float(data.get("volume", 0)),
        "highPrice": float(data.get("highPrice", 0)),
        "lowPrice": float(data.get("lowPrice", 0)),
    }


def obtener_book(symbol: str, limit: int = 20) -> dict:
    data = _request_json("/depth", {"symbol": symbol.upper(), "limit": int(limit)})
    bids = [[float(p), float(q)] for p, q in data.get("bids", [])]
    asks = [[float(p), float(q)] for p, q in data.get("asks", [])]
    bid_total = sum(p * q for p, q in bids)
    ask_total = sum(p * q for p, q in asks)
    imbalance = 0.0
    if (bid_total + ask_total) > 0:
        imbalance = (bid_total - ask_total) / (bid_total + ask_total)
    return {
        "bids": bids[:5],
        "asks": asks[:5],
        "bid_total_usdt": round(bid_total, 2),
        "ask_total_usdt": round(ask_total, 2),
        "imbalance": round(imbalance, 4),
    }


def obtener_klines(symbol: str, interval: str = INTERVAL, limit: int = LIMIT) -> list[dict]:
    raw = _request_json("/klines", {
        "symbol": symbol.upper(),
        "interval": interval,
        "limit": min(int(limit), 500),
    })
    velas = []
    for k in raw:
        velas.append({
            "open_time": int(k[0]),
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "volume": float(k[5]),
            "close_time": int(k[6]),
            "quote_volume": float(k[7]),
            "trades": int(k[8]),
        })
    return velas


def _sma(values: list[float], period: int) -> float:
    if not values:
        return 0.0
    return float(mean(values[-period:])) if len(values) >= period else float(mean(values))


def _ema(values: list[float], period: int) -> float:
    if not values:
        return 0.0
    if len(values) < period:
        return float(mean(values))
    alpha = 2 / (period + 1)
    ema = float(mean(values[:period]))
    for value in values[period:]:
        ema = (value * alpha) + (ema * (1 - alpha))
    return float(ema)


def _rsi(closes: list[float], period: int = 14) -> float:
    if len(closes) <= period:
        return 50.0
    gains, losses = [], []
    cambios = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    for c in cambios[-period:]:
        gains.append(max(c, 0))
        losses.append(abs(min(c, 0)))
    avg_gain = mean(gains) if gains else 0
    avg_loss = mean(losses) if losses else 0
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return float(100 - (100 / (1 + rs)))


def _macd(closes: list[float]) -> dict:
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    macd_line = ema12 - ema26
    macd_series = []
    for i in range(26, len(closes) + 1):
        subset = closes[:i]
        macd_series.append(_ema(subset, 12) - _ema(subset, 26))
    signal = _ema(macd_series, 9) if macd_series else 0.0
    return {
        "macd": float(macd_line),
        "macd_signal": float(signal),
        "macd_histogram": float(macd_line - signal),
    }


def _bollinger(closes: list[float], period: int = 20, mult: float = 2.0) -> dict:
    if not closes:
        return {"bollinger_mid": 0, "bollinger_upper": 0, "bollinger_lower": 0}
    window = closes[-period:] if len(closes) >= period else closes
    mid = mean(window)
    sd = pstdev(window) if len(window) > 1 else 0
    return {
        "bollinger_mid": float(mid),
        "bollinger_upper": float(mid + mult * sd),
        "bollinger_lower": float(mid - mult * sd),
    }


def _vwap(velas: list[dict]) -> float:
    pv = 0.0
    vol = 0.0
    for v in velas:
        typical = (v["high"] + v["low"] + v["close"]) / 3
        pv += typical * v["volume"]
        vol += v["volume"]
    return float(pv / vol) if vol else 0.0


def _atr(velas: list[dict], period: int = 14) -> float:
    if len(velas) < 2:
        return 0.0
    trs = []
    for i in range(1, len(velas)):
        h, l = velas[i]["high"], velas[i]["low"]
        prev_close = velas[i - 1]["close"]
        trs.append(max(h - l, abs(h - prev_close), abs(l - prev_close)))
    window = trs[-period:] if len(trs) >= period else trs
    return float(mean(window)) if window else 0.0


def _volatilidad_extrema(velas: list[dict]) -> bool:
    if len(velas) < 45:
        return False
    atr_actual = _atr(velas[-15:], 14)
    atrs = []
    for i in range(15, len(velas)):
        atrs.append(_atr(velas[i - 14:i + 1], 14))
    if len(atrs) < 20:
        return False
    media_atr = mean(atrs)
    sd_atr = pstdev(atrs) if len(atrs) > 1 else 0
    return atr_actual > (media_atr + 3 * sd_atr)


def calcular_indicadores(velas: list[dict]) -> dict:
    closes = [v["close"] for v in velas]
    indicadores = {
        "precio_actual": closes[-1] if closes else 0.0,
        "rsi14": _rsi(closes, 14),
        "ema20": _ema(closes, 20),
        "sma50": _sma(closes, 50),
        "vwap": _vwap(velas),
        "atr14": _atr(velas, 14),
    }
    indicadores.update(_macd(closes))
    indicadores.update(_bollinger(closes, 20, 2))
    return {k: round(v, 6) if isinstance(v, float) else v for k, v in indicadores.items()}


def _clasificar_tendencia(ind: dict) -> str:
    precio = ind.get("precio_actual", 0)
    ema20 = ind.get("ema20", 0)
    sma50 = ind.get("sma50", 0)
    macd_hist = ind.get("macd_histogram", 0)
    if precio > ema20 > sma50 and macd_hist > 0:
        return "alcista"
    if precio < ema20 < sma50 and macd_hist < 0:
        return "bajista"
    return "lateral"


def _clasificar_volumen(ticker: dict) -> str:
    qv = float(ticker.get("quoteVolume", 0))
    if qv >= 50_000_000:
        return "alto"
    if qv >= 5_000_000:
        return "medio"
    return "bajo"


def _clasificar_volatilidad(velas: list[dict]) -> str:
    closes = [v["close"] for v in velas]
    if len(closes) < 10:
        return "media"
    retornos = []
    for i in range(1, len(closes)):
        if closes[i - 1] > 0:
            retornos.append(math.log(closes[i] / closes[i - 1]))
    if not retornos:
        return "media"
    sd = pstdev(retornos[-50:]) if len(retornos) >= 2 else 0
    if sd > 0.025:
        return "alta"
    if sd < 0.007:
        return "baja"
    return "media"


def analizar_mercado(symbol: str, interval: str = INTERVAL) -> dict:
    symbol = symbol.upper()
    ticker = obtener_ticker_24h(symbol)
    velas = obtener_klines(symbol, interval=interval, limit=LIMIT)
    book = obtener_book(symbol, limit=20)

    indicadores = calcular_indicadores(velas)
    precio_actual = float(ticker.get("lastPrice") or indicadores.get("precio_actual", 0))
    indicadores["precio_actual"] = precio_actual

    quote_volume = float(ticker.get("quoteVolume", 0))
    liquidez_ok = quote_volume >= LIQUIDEZ_MINIMA_USDT
    advertencia_volatilidad = _volatilidad_extrema(velas)

    return {
        "symbol": symbol,
        "precio_actual": precio_actual,
        "ticker_24h": ticker,
        "cambio_pct": ticker.get("priceChangePercent", 0),
        "liquidez_24h_usdt": quote_volume,
        "book": book,
        "velas": velas[-60:],
        "indicadores": indicadores,
        "tendencia": _clasificar_tendencia(indicadores),
        "volumen": _clasificar_volumen(ticker),
        "volatilidad": _clasificar_volatilidad(velas),
        "liquidez_suficiente": liquidez_ok,
        "mensaje_liquidez": "" if liquidez_ok else "Liquidez insuficiente para análisis confiable.",
        "advertencia_volatilidad": advertencia_volatilidad,
        "aviso_volatilidad": "Advertencia: volatilidad extrema detectada." if advertencia_volatilidad else "",
    }


def estado_binance() -> dict:
    started = time.time()
    precio = obtener_precio_actual("BTCUSDT")
    return {
        "estado": "online",
        "latencia_ms": round((time.time() - started) * 1000, 2),
        "precio_btcusdt": precio,
        "cache_items": len(_cache),
    }
