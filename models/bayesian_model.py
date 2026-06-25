"""
models/bayesian_model.py
Motor bayesiano liviano para CryptoAdvisor.

No usa pandas/numpy/pgmpy para que el proyecto ejecute fácil en Windows.
Representa P(Recomendacion | Tendencia, Volumen, Volatilidad, Acción, Indicadores)
con un enfoque Naive Bayes + ajuste técnico.
"""

from __future__ import annotations

import json
import os

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "training_data.json")

PERFILES = {
    "conservador": 0.80,
    "moderado": 0.70,
    "agresivo": 0.60,
}


def _cargar_muestras() -> list[dict]:
    try:
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            datos = json.load(f)
        return datos.get("samples", [])
    except Exception:
        return []


def _normalizar_accion(accion: str) -> str:
    mapa = {
        "comprar": "BUY",
        "vender": "SELL",
        "esperar": "HOLD",
        "buy": "BUY",
        "sell": "SELL",
        "hold": "HOLD",
    }
    return mapa.get((accion or "").lower(), "HOLD")


def _prob_exito_naive_bayes(tendencia, volumen, volatilidad, accion) -> float:
    muestras = _cargar_muestras()
    if not muestras:
        return 0.50

    alpha = 1
    clases = ["exitoso", "fallido"]

    def contar(**filtros):
        return sum(1 for m in muestras if all(m.get(k) == v for k, v in filtros.items()))

    total = len(muestras)
    priors = {
        clase: (contar(resultado=clase) + alpha) / (total + alpha * len(clases))
        for clase in clases
    }

    evidencias = {
        "tendencia": tendencia,
        "volumen": volumen,
        "volatilidad": volatilidad,
        "accion": accion,
    }

    numeradores = {}
    for clase in clases:
        subset = [m for m in muestras if m.get("resultado") == clase]
        n_clase = len(subset)
        likelihood = 1.0
        for col, val in evidencias.items():
            categorias = {m.get(col) for m in muestras if m.get(col) is not None}
            n_cat = max(len(categorias), 1)
            n_val = sum(1 for m in subset if m.get(col) == val)
            likelihood *= (n_val + alpha) / (n_clase + alpha * n_cat)
        numeradores[clase] = priors[clase] * likelihood

    denom = numeradores["exitoso"] + numeradores["fallido"]
    return round(numeradores["exitoso"] / denom, 4) if denom else 0.50


def _score_indicadores(ind: dict) -> dict:
    rsi = float(ind.get("rsi14", 50) or 50)
    macd_hist = float(ind.get("macd_histogram", 0) or 0)
    precio = float(ind.get("precio_actual", 0) or 0)
    ema20 = float(ind.get("ema20", 0) or 0)
    sma50 = float(ind.get("sma50", 0) or 0)
    vwap = float(ind.get("vwap", 0) or 0)
    upper = float(ind.get("bollinger_upper", 0) or 0)
    lower = float(ind.get("bollinger_lower", 0) or 0)

    buy = 0.33
    sell = 0.33
    hold = 0.34

    if rsi < 30:
        buy += 0.18; sell -= 0.06; hold -= 0.04
    elif rsi > 70:
        sell += 0.18; buy -= 0.06; hold -= 0.04
    else:
        hold += 0.08

    if macd_hist > 0:
        buy += 0.12; sell -= 0.05
    elif macd_hist < 0:
        sell += 0.12; buy -= 0.05
    else:
        hold += 0.06

    if ema20 > sma50:
        buy += 0.08
    elif ema20 < sma50:
        sell += 0.08

    if precio and vwap:
        if precio > vwap:
            buy += 0.04
        elif precio < vwap:
            sell += 0.04

    if lower and precio < lower:
        buy += 0.09
    if upper and precio > upper:
        sell += 0.09

    vals = {"BUY": max(buy, 0.01), "SELL": max(sell, 0.01), "HOLD": max(hold, 0.01)}
    s = sum(vals.values())
    return {k: round(v / s, 4) for k, v in vals.items()}


def inferir_recomendacion(tendencia, volumen, volatilidad, accion, indicadores=None, perfil_riesgo="moderado"):
    indicadores = indicadores or {}
    perfil_riesgo = (perfil_riesgo or "moderado").lower()
    umbral = PERFILES.get(perfil_riesgo, 0.70)

    accion_objetivo = _normalizar_accion(accion)
    p_exito = _prob_exito_naive_bayes(tendencia, volumen, volatilidad, accion)
    probs_tecnicas = _score_indicadores(indicadores)

    # Mezcla evidencia bayesiana histórica con evidencia técnica actual.
    probs = {}
    for rec in ["BUY", "SELL", "HOLD"]:
        peso_accion = p_exito if rec == accion_objetivo else (1 - p_exito) / 2
        probs[rec] = (0.55 * probs_tecnicas[rec]) + (0.45 * peso_accion)

    # Ajuste por contexto de mercado
    if tendencia == "alcista":
        probs["BUY"] += 0.05
    elif tendencia == "bajista":
        probs["SELL"] += 0.05
    else:
        probs["HOLD"] += 0.05

    if volatilidad == "alta":
        probs["HOLD"] += 0.06

    total = sum(max(v, 0.01) for v in probs.values())
    probs = {k: round(max(v, 0.01) / total, 4) for k, v in probs.items()}

    mejor = max(probs, key=probs.get)
    confianza = probs[mejor]

    # Regla de perfil de riesgo: si no supera umbral, HOLD.
    recomendacion = mejor if confianza >= umbral else "HOLD"
    if recomendacion == "HOLD":
        confianza = max(probs["HOLD"], 1 - max(probs["BUY"], probs["SELL"]))

    if confianza >= 0.80:
        nivel = "Alta"
        color = "success"
    elif confianza >= 0.60:
        nivel = "Media"
        color = "warning"
    else:
        nivel = "Baja"
        color = "secondary"

    return {
        "recomendacion": recomendacion,
        "probabilidades": probs,
        "probabilidad": round(confianza, 4),
        "probabilidad_pct": round(confianza * 100, 2),
        "confianza": nivel,
        "color": color,
        "umbral_perfil": umbral,
        "perfil_riesgo": perfil_riesgo,
        "variables": {
            "tendencia": tendencia,
            "volumen": volumen,
            "volatilidad": volatilidad,
            "accion_evaluada": accion_objetivo,
        },
    }


def predecir(tendencia, volumen, volatilidad, accion, indicadores=None, perfil_riesgo="moderado"):
    return inferir_recomendacion(tendencia, volumen, volatilidad, accion, indicadores, perfil_riesgo)
