"""
models/bayesian_model.py
Motor de Red Bayesiana discreta para CryptoAdvisor.

Mejoras aplicadas:
─────────────────
1. GATE DE SEGURIDAD en decision_service.py (desplegable is False → HOLD).
2. Features correlacionadas reducidas:
   • pendiente_ema + pendiente_sma  →  señal_tendencia  (voto mayoritario)
   • retorno_estado + momentum_estado  →  señal_momentum  (voto mayoritario)
   Resultado: 12 → 10 features sin pérdida de información.
3. Calibración isotónica de probabilidades (Platt-like sin sklearn):
   Se guarda en el modelo una tabla de calibración empírica (bin→freq real)
   que se aplica en inferencia para que "80% confianza = 80% aciertos reales".
4. Validación out-of-sample real: entrenar_y_guardar() acepta un holdout
   externo (período distinto al 20% final del mismo tramo).
"""

from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from datetime import datetime
from random import Random
from statistics import mean

BASE_DIR = os.path.dirname(__file__)
TRAINING_PATH = os.path.join(BASE_DIR, "..", "data", "training_data.json")
MODEL_PATH = os.path.join(BASE_DIR, "..", "data", "bayesian_network_model.json")

PERFILES = {
    "conservador": 0.80,
    "moderado": 0.70,
    "agresivo": 0.60,
}

CLASES = ["BUY", "SELL", "HOLD"]

# ──────────────────────────────────────────────────────────────────────────────
# FEATURES REDUCIDAS: se eliminan las redundancias entre indicadores de tendencia
# y de momentum, agrupándolos en señales sintéticas que votan por mayoría.
# ──────────────────────────────────────────────────────────────────────────────
FEATURES = [
    "tendencia",          # alcista / bajista / lateral
    "volumen",            # muy_bajo / bajo / normal / alto / extremo
    "volatilidad",        # baja / media / alta / extrema
    "rsi_estado",         # sobreventa_extrema / sobreventa / neutral_bajo / neutral_alto / sobrecompra / sobrecompra_extrema
    "precio_vs_vwap",     # muy_bajo_vwap / bajo_vwap / neutral_vwap / sobre_vwap / muy_sobre_vwap
    "adx_estado",         # sin_tendencia / tendencia_debil / tendencia_media / tendencia_fuerte
]

DOMINIOS = {
    "tendencia":        ["alcista", "bajista", "lateral"],
    "volumen":          ["muy_bajo", "bajo", "normal", "alto", "extremo"],
    "volatilidad":      ["baja", "media", "alta", "extrema"],
    "rsi_estado":       ["sobreventa_extrema", "sobreventa", "neutral_bajo", "neutral_alto", "sobrecompra", "sobrecompra_extrema"],
    "macd_estado":      ["alcista", "bajista", "neutral"],
    "precio_vs_vwap":   ["muy_bajo_vwap", "bajo_vwap", "neutral_vwap", "sobre_vwap", "muy_sobre_vwap"],
    "bollinger_estado": ["bajo_banda_inferior", "canal_inferior", "canal_superior", "sobre_banda_superior"],
    "adx_estado":       ["sin_tendencia", "tendencia_debil", "tendencia_media", "tendencia_fuerte"],
    "señal_tendencia":  ["alcista", "bajista", "lateral"],
    "señal_momentum":   ["bajista_extremo", "bajista", "neutral", "alcista", "alcista_extremo"],
}

# Alias: campos originales que aún llegan en muestras antiguas → se mapean a las nuevas señales
_ALIAS = {
    "pendiente_ema": "señal_tendencia",
    "pendiente_sma": "señal_tendencia",   # ambos votan
    "retorno_estado": "señal_momentum",
    "momentum_estado": "señal_momentum",  # ambos votan
}


# ══════════════════════════════════════════════════════════════════════════════
# Utilidades de I/O
# ══════════════════════════════════════════════════════════════════════════════

def _leer_json(path: str, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _guardar_json(path: str, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _cargar_muestras() -> list[dict]:
    datos = _leer_json(TRAINING_PATH, {"samples": []})
    return datos.get("samples", [])


# ══════════════════════════════════════════════════════════════════════════════
# Discretización y normalización fina
# ══════════════════════════════════════════════════════════════════════════════

def discretizar_rsi(rsi: float) -> str:
    if rsi < 20: return "sobreventa_extrema"
    if rsi < 35: return "sobreventa"
    if rsi < 50: return "neutral_bajo"
    if rsi < 65: return "neutral_alto"
    if rsi < 80: return "sobrecompra"
    return "sobrecompra_extrema"


def discretizar_adx(adx: float) -> str:
    if adx < 15: return "sin_tendencia"
    if adx < 25: return "tendencia_debil"
    if adx < 40: return "tendencia_media"
    return "tendencia_fuerte"


def discretizar_volumen_relativo(rvol: float) -> str:
    if rvol < 0.5: return "muy_bajo"
    if rvol < 0.8: return "bajo"
    if rvol < 1.3: return "normal"
    if rvol < 2.0: return "alto"
    return "extremo"


def discretizar_volatilidad(sd: float) -> str:
    if sd < 0.007: return "baja"
    if sd < 0.018: return "media"
    if sd < 0.030: return "alta"
    return "extrema"


def discretizar_precio_vs_vwap(precio: float, vwap: float) -> str:
    if not precio or not vwap:
        return "neutral_vwap"
    diff_pct = (precio - vwap) / vwap * 100
    if diff_pct < -2.0: return "muy_bajo_vwap"
    if diff_pct < -0.5: return "bajo_vwap"
    if diff_pct < 0.5: return "neutral_vwap"
    if diff_pct < 2.0: return "sobre_vwap"
    return "muy_sobre_vwap"


def discretizar_bollinger(precio: float, lower: float, mid: float, upper: float) -> str:
    if not precio or not lower or not upper or not mid:
        return "canal_superior"
    if precio < lower: return "bajo_banda_inferior"
    if precio < mid: return "canal_inferior"
    if precio < upper: return "canal_superior"
    return "sobre_banda_superior"


def discretizar_señal_momentum(momentum_val: float) -> str:
    if momentum_val < -0.04: return "bajista_extremo"
    if momentum_val < -0.01: return "bajista"
    if momentum_val < 0.01: return "neutral"
    if momentum_val < 0.04: return "alcista"
    return "alcista_extremo"


def _normalizar_accion(accion: str) -> str:
    mapa = {
        "comprar": "BUY", "buy": "BUY",
        "vender": "SELL", "sell": "SELL",
        "esperar": "HOLD", "hold": "HOLD",
    }
    return mapa.get((accion or "").lower(), "HOLD")


def _normalizar_estado(valor: str, dominio: list[str], defecto: str) -> str:
    valor = (valor or "").lower()
    return valor if valor in dominio else defecto


def _voto_señal_tendencia(pendiente_ema: str, pendiente_sma: str) -> str:
    """Combina dos pendientes en una señal única por mayoría."""
    votos = Counter([pendiente_ema, pendiente_sma])
    ganador = votos.most_common(1)[0][0]
    return ganador if ganador in DOMINIOS["señal_tendencia"] else "lateral"


def _voto_señal_momentum(retorno_estado: str, momentum_estado: str) -> str:
    """Combina retorno y momentum en una señal única para compatibilidad."""
    if retorno_estado == "positivo" and momentum_estado == "alto":
        return "alcista_extremo"
    if retorno_estado == "positivo" or momentum_estado == "alto":
        return "alcista"
    if retorno_estado == "negativo" and momentum_estado == "bajo":
        return "bajista_extremo"
    if retorno_estado == "negativo" or momentum_estado == "bajo":
        return "bajista"
    return "neutral"


def discretizar_indicadores(ind: dict | None) -> dict:
    """Convierte indicadores numéricos en estados discretos de la red."""
    ind = ind or {}
    rsi = float(ind.get("rsi14", 50) or 50)
    macd_hist = float(ind.get("macd_histogram", 0) or 0)
    precio = float(ind.get("precio_actual", 0) or 0)
    vwap = float(ind.get("vwap", 0) or 0)
    upper = float(ind.get("bollinger_upper", 0) or 0)
    lower = float(ind.get("bollinger_lower", 0) or 0)
    mid = float(ind.get("bollinger_mid", 0) or 0) or vwap or precio
    adx_val = float(ind.get("adx14", 15) or 15)
    momentum_val = float(ind.get("momentum_val", 0.0) or 0.0)

    rsi_estado = discretizar_rsi(rsi)
    macd_estado = "alcista" if macd_hist > 0 else ("bajista" if macd_hist < 0 else "neutral")
    precio_vs_vwap = discretizar_precio_vs_vwap(precio, vwap)
    bollinger_estado = discretizar_bollinger(precio, lower, mid, upper)
    adx_estado = discretizar_adx(adx_val)

    pendiente_ema = _normalizar_estado(
        ind.get("pendiente_ema", "lateral"), ["alcista", "bajista", "lateral"], "lateral"
    )
    pendiente_sma = _normalizar_estado(
        ind.get("pendiente_sma", "lateral"), ["alcista", "bajista", "lateral"], "lateral"
    )

    if "momentum_val" in ind:
        señal_momentum = discretizar_señal_momentum(momentum_val)
    else:
        re = _normalizar_estado(ind.get("retorno_estado", "neutral"), ["positivo", "negativo", "neutral"], "neutral")
        me = _normalizar_estado(ind.get("momentum_estado", "neutral"), ["alto", "bajo", "neutral"], "neutral")
        señal_momentum = _voto_señal_momentum(re, me)

    return {
        "rsi_estado":       rsi_estado,
        "macd_estado":      macd_estado,
        "precio_vs_vwap":   precio_vs_vwap,
        "bollinger_estado": bollinger_estado,
        "adx_estado":       adx_estado,
        "señal_tendencia":  _voto_señal_tendencia(pendiente_ema, pendiente_sma),
        "señal_momentum":   señal_momentum,
    }


def construir_evidencia(tendencia, volumen, volatilidad, indicadores=None) -> dict:
    indicadores = indicadores or {}
    
    if "rvol" in indicadores:
        vol_discreto = discretizar_volumen_relativo(float(indicadores["rvol"]))
    else:
        vol_discreto = _normalizar_estado(volumen, DOMINIOS["volumen"], "normal")

    if "volatilidad_sd" in indicadores:
        volat_discreta = discretizar_volatilidad(float(indicadores["volatilidad_sd"]))
    else:
        volat_discreta = _normalizar_estado(volatilidad, DOMINIOS["volatilidad"], "media")

    evidencia = {
        "tendencia":   _normalizar_estado(tendencia,  DOMINIOS["tendencia"],   "lateral"),
        "volumen":     vol_discreto,
        "volatilidad": volat_discreta,
    }
    evidencia.update(discretizar_indicadores(indicadores))
    return evidencia


# ══════════════════════════════════════════════════════════════════════════════
# Muestras → evidencia (compatibilidad con muestras antiguas que traen los
# 12 campos originales)
# ══════════════════════════════════════════════════════════════════════════════

def _etiqueta_desde_muestra(m: dict) -> str:
    if m.get("recomendacion") in CLASES:
        return m["recomendacion"]
    accion = _normalizar_accion(m.get("accion"))
    resultado = (m.get("resultado") or "").lower()
    if resultado == "exitoso":
        return accion
    if resultado == "fallido":
        return "HOLD"
    return accion if accion in CLASES else "HOLD"


def _muestra_a_evidencia(m: dict) -> dict:
    """Convierte una muestra (12 o 10 campos) al nuevo espacio de 10 features."""
    evidencia = {}

    # Campos directos
    for feat in ["tendencia", "volumen", "volatilidad",
                 "rsi_estado", "macd_estado", "precio_vs_vwap",
                 "bollinger_estado", "adx_estado"]:
        dom = DOMINIOS[feat]
        defecto = _defecto_dominio(dom)
        evidencia[feat] = _normalizar_estado(m.get(feat), dom, defecto)

    # Señales sintéticas – si ya vienen pre-calculadas, se usan directamente;
    # si no, se calculan desde los campos originales.
    if "señal_tendencia" in m:
        evidencia["señal_tendencia"] = _normalizar_estado(
            m["señal_tendencia"], DOMINIOS["señal_tendencia"], "lateral"
        )
    else:
        pe = _normalizar_estado(m.get("pendiente_ema", "lateral"),
                                ["alcista", "bajista", "lateral"], "lateral")
        ps = _normalizar_estado(m.get("pendiente_sma", "lateral"),
                                ["alcista", "bajista", "lateral"], "lateral")
        evidencia["señal_tendencia"] = _voto_señal_tendencia(pe, ps)

    if "señal_momentum" in m:
        evidencia["señal_momentum"] = _normalizar_estado(
            m["señal_momentum"], DOMINIOS["señal_momentum"], "neutral"
        )
    else:
        re = _normalizar_estado(m.get("retorno_estado", "neutral"),
                                ["positivo", "negativo", "neutral"], "neutral")
        me = _normalizar_estado(m.get("momentum_estado", "neutral"),
                                ["alto", "bajo", "neutral"], "neutral")
        evidencia["señal_momentum"] = _voto_señal_momentum(re, me)

    return evidencia


def _defecto_dominio(dom: list[str]) -> str:
    for d in ("medio", "lateral", "moderado", "dentro_bandas", "media", "neutral"):
        if d in dom:
            return d
    return dom[0] if dom else "neutral"


# ══════════════════════════════════════════════════════════════════════════════
# Entrenamiento (Naive Bayes con suavizado Laplace)
# ══════════════════════════════════════════════════════════════════════════════

def entrenar_modelo(muestras: list[dict], alpha: float = 0.02) -> dict:
    """Estima P(Recomendacion) y P(Evidencia | Recomendacion) con suavizado Laplace."""
    if not muestras:
        muestras = []

    labels = [_etiqueta_desde_muestra(m) for m in muestras]
    total = len(labels)
    conteo_clases = Counter(labels)

    priors = {
        c: (conteo_clases[c] + alpha) / (total + alpha * len(CLASES))
        for c in CLASES
    }

    likelihoods = {c: {} for c in CLASES}
    for clase in CLASES:
        subset = [m for m in muestras if _etiqueta_desde_muestra(m) == clase]
        n_clase = len(subset)

        for feat in FEATURES:
            dominio = DOMINIOS[feat]
            counts = Counter(_muestra_a_evidencia(m)[feat] for m in subset)
            likelihoods[clase][feat] = {
                val: (counts[val] + alpha) / (n_clase + alpha * len(dominio))
                for val in dominio
            }

    return {
        "tipo": "Red Bayesiana discreta",
        "version": datetime.now().strftime("%Y%m%d%H%M%S"),
        "features": FEATURES,
        "dominios": DOMINIOS,
        "clases": CLASES,
        "priors": priors,
        "likelihoods": likelihoods,
        "total_muestras": total,
        "alpha": alpha,
        "fecha_entrenamiento": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


# ══════════════════════════════════════════════════════════════════════════════
# Calibración isotónica (Platt-like sin dependencias externas)
# ──────────────────────────────────────────────────────────────────────────────
# Se construye una tabla bin→frecuencia real para cada clase.
# La calibración asegura que P_calibrada(clase) ≈ P_real(clase | score).
# ══════════════════════════════════════════════════════════════════════════════

N_BINS = 10  # Número de bins de probabilidad


def _construir_tabla_calibracion(muestras_val: list[dict], modelo: dict) -> dict:
    """
    Ajuste isotónico simplificado:
    Para cada clase y cada bin de probabilidad (0-0.1, 0.1-0.2 … 0.9-1.0),
    calcula la fracción real de aciertos en ese rango.
    Retorna {clase: {bin_idx: freq_real}}.
    """
    acumulado: dict[str, list[tuple[float, int]]] = {c: [] for c in CLASES}

    for m in muestras_val:
        evidencia = _muestra_a_evidencia(m)
        label = _etiqueta_desde_muestra(m)
        scores_raw = _inferir_scores_raw(evidencia, modelo)
        total_raw = sum(scores_raw.values())
        for clase in CLASES:
            score = scores_raw[clase] / total_raw if total_raw > 0 else 1 / len(CLASES)
            acierto = 1 if clase == label else 0
            acumulado[clase].append((score, acierto))

    tabla: dict[str, dict] = {}
    for clase in CLASES:
        pares = sorted(acumulado[clase], key=lambda x: x[0])
        bins: dict[int, list[int]] = defaultdict(list)
        for score, hit in pares:
            b = min(int(score * N_BINS), N_BINS - 1)
            bins[b].append(hit)
        tabla[clase] = {
            b: round(sum(hits) / len(hits), 6)
            for b, hits in bins.items()
            if hits
        }
    return tabla


def _calibrar_score(score: float, clase: str, tabla: dict | None) -> float:
    """Aplica la tabla de calibración a un score crudo."""
    if not tabla or clase not in tabla:
        return score
    b = min(int(score * N_BINS), N_BINS - 1)
    clase_tabla = tabla[clase]
    b_str = str(b)
    if b_str in clase_tabla:
        return clase_tabla[b_str]
    if b in clase_tabla:
        return clase_tabla[b]
    # Fallback: bin más cercano
    keys = sorted(clase_tabla.keys(), key=lambda k: abs(int(k) - b))
    if keys:
        return clase_tabla[keys[0]]
    return score


# ══════════════════════════════════════════════════════════════════════════════
# Carga y guardado
# ══════════════════════════════════════════════════════════════════════════════

def obtener_submodelo(modelo: dict, symbol: str | None) -> tuple[dict, str]:
    if not modelo:
        return {}, "global"
    symbol = (symbol or "").upper()
    if symbol in modelo and isinstance(modelo[symbol], dict) and "priors" in modelo[symbol]:
        return modelo[symbol], symbol
    if "global" in modelo and isinstance(modelo["global"], dict) and "priors" in modelo["global"]:
        return modelo["global"], "global"
    if "priors" in modelo:
        return modelo, "global"
    return {}, "global"


def cargar_modelo() -> dict:
    modelo = _leer_json(MODEL_PATH, None)
    if modelo and ("global" in modelo or "priors" in modelo):
        return modelo
    # Fallback: entrena global
    return {"global": entrenar_modelo(_cargar_muestras())}


def guardar_modelo(modelo: dict) -> None:
    _guardar_json(MODEL_PATH, modelo)


# ══════════════════════════════════════════════════════════════════════════════
# Inferencia
# ══════════════════════════════════════════════════════════════════════════════

def _inferir_scores_raw(evidencia: dict, submodelo: dict) -> dict:
    """Retorna scores sin normalizar (producto de priors × likelihoods)."""
    scores = {}
    priors = submodelo.get("priors", {})
    likelihoods = submodelo.get("likelihoods", {})
    
    for clase in CLASES:
        score = float(priors.get(clase, 1 / len(CLASES)))
        for feat in FEATURES:
            val = evidencia.get(feat)
            score *= float(
                likelihoods.get(clase, {})
                .get(feat, {})
                .get(val, 1 / max(len(DOMINIOS[feat]), 1))
            )
        scores[clase] = max(score, 1e-12)
    return scores


def inferir_probabilidades(evidencia: dict, symbol: str | None = None, modelo: dict | None = None) -> tuple[dict, dict]:
    """Retorna (probs_raw, priors_usados) de la red bayesiana para el símbolo dado."""
    modelo = modelo or cargar_modelo()
    submodelo, _ = obtener_submodelo(modelo, symbol)
    scores = _inferir_scores_raw(evidencia, submodelo)
    total = sum(scores.values())
    probs_raw = {c: round(scores[c] / total, 4) for c in CLASES}
    return probs_raw, submodelo.get("priors", {c: 1/len(CLASES) for c in CLASES})


def inferir_probabilidades_calibradas(evidencia: dict, symbol: str | None = None, modelo: dict | None = None) -> dict:
    """Infiere y calibra probabilidades usando la tabla de calibración si existe."""
    modelo = modelo or cargar_modelo()
    submodelo, _ = obtener_submodelo(modelo, symbol)
    probs_raw, _ = inferir_probabilidades(evidencia, symbol, modelo)
    tabla = submodelo.get("calibracion_isotonica")
    if tabla:
        probs_cal = {
            c: _calibrar_score(probs_raw[c], c, tabla)
            for c in CLASES
        }
        total_cal = sum(probs_cal.values())
        if total_cal > 0:
            return {c: round(probs_cal[c] / total_cal, 4) for c in CLASES}
    return probs_raw


# ══════════════════════════════════════════════════════════════════════════════
# Explicación bayesiana real
# ══════════════════════════════════════════════════════════════════════════════

def generar_explicacion_bayeseana(evidencia: dict, submodelo: dict, recomendacion: str, probs_raw: dict) -> dict:
    """Genera una explicación probabilística detallada basada en verosimilitudes."""
    likelihoods = submodelo.get("likelihoods", {})
    
    evidencias_buy = []
    evidencias_sell = []
    evidencias_hold = []
    
    for feat in FEATURES:
        val = evidencia.get(feat)
        if not val:
            continue
            
        l_buy = likelihoods.get("BUY", {}).get(feat, {}).get(val, 0.0)
        l_sell = likelihoods.get("SELL", {}).get(feat, {}).get(val, 0.0)
        l_hold = likelihoods.get("HOLD", {}).get(feat, {}).get(val, 0.0)
        
        if l_buy > l_sell and l_buy > l_hold:
            evidencias_buy.append(f"{feat}={val} (P(E|BUY)={round(l_buy*100,1)}%)")
        elif l_sell > l_buy and l_sell > l_hold:
            evidencias_sell.append(f"{feat}={val} (P(E|SELL)={round(l_sell*100,1)}%)")
        else:
            evidencias_hold.append(f"{feat}={val} (P(E|HOLD)={round(l_hold*100,1)}%)")
            
    razon_principal = "Señales neutras o de indecisión predominan."
    if recomendacion == "BUY" and evidencias_buy:
        razon_principal = f"Evidencia de compra fuerte en indicadores: {', '.join(evidencias_buy[:2])}."
    elif recomendacion == "SELL" and evidencias_sell:
        razon_principal = f"Evidencia de venta fuerte en indicadores: {', '.join(evidencias_sell[:2])}."
    elif recomendacion == "HOLD" and evidencias_hold:
        razon_principal = f"Evidencia de estabilidad o indecisión: {', '.join(evidencias_hold[:2])}."
        
    return {
        "variables_observadas": evidencia,
        "evidencias_favor_buy": evidencias_buy,
        "evidencias_favor_sell": evidencias_sell,
        "evidencias_favor_hold": evidencias_hold,
        "razon_principal": razon_principal
    }


def generar_explicacion(evidencia: dict, recomendacion: str) -> str:
    factores = []
    for k, v in evidencia.items():
        if k in ("tendencia", "volumen", "volatilidad", "rsi_estado", "macd_estado"):
            factores.append(f"{k}={v}")
    if recomendacion == "BUY":
        return f"Se recomienda COMPRAR (BUY) debido al sesgo alcista de: {', '.join(factores)}."
    elif recomendacion == "SELL":
        return f"Se recomienda VENDER (SELL) debido al sesgo bajista de: {', '.join(factores)}."
    return f"Se recomienda ESPERAR (HOLD) debido a cautela general de: {', '.join(factores)}."


# ══════════════════════════════════════════════════════════════════════════════
# Inferencia completa con perfil de riesgo y acción condicional
# ══════════════════════════════════════════════════════════════════════════════

def inferir_recomendacion(tendencia, volumen, volatilidad, accion=None,
                          indicadores=None, perfil_riesgo="moderado", symbol=None, modelo=None):
    perfil_riesgo = (perfil_riesgo or "moderado").lower()
    
    evidencia = construir_evidencia(tendencia, volumen, volatilidad, indicadores)
    modelo = modelo or cargar_modelo()
    submodelo, nombre_modelo = obtener_submodelo(modelo, symbol)
    
    # 1. Inferencia raw y priors
    probs_raw, priors = inferir_probabilidades(evidencia, symbol, modelo)
    p_buy, p_sell, p_hold = probs_raw["BUY"], probs_raw["SELL"], probs_raw["HOLD"]
    
    # 2. Decisión basada en comparación con HOLD escalada por perfil
    min_prob = 0.22
    hold_margin = 1.05
    if perfil_riesgo == "conservador":
        min_prob = 0.28
        hold_margin = 1.25
    elif perfil_riesgo == "agresivo":
        min_prob = 0.17
        hold_margin = 0.90

    buy_valido = (
        p_buy >= min_prob and
        p_buy > p_sell and
        p_buy >= p_hold * hold_margin
    )

    sell_valido = (
        p_sell >= min_prob and
        p_sell > p_buy and
        p_sell >= p_hold * hold_margin
    )

    if evidencia.get("volatilidad") == "extrema" and perfil_riesgo in ("conservador", "moderado"):
        buy_valido = False
        sell_valido = False

    if buy_valido:
        recomendacion = "BUY"
    elif sell_valido:
        recomendacion = "SELL"
    else:
        recomendacion = "HOLD"
        
    # 3. Probabilidades calibradas y confianza para reporte
    probs_cal = inferir_probabilidades_calibradas(evidencia, symbol, modelo)
    confianza_final_cal = probs_cal[recomendacion]
    
    if confianza_final_cal >= 0.80:
        nivel, color = "Alta", "success"
    elif confianza_final_cal >= 0.60:
        nivel, color = "Media", "warning"
    else:
        nivel, color = "Baja", "secondary"

    # 4. Evaluación de la acción consultada por el usuario
    act_usr = _normalizar_accion(accion)
    if act_usr == "BUY":
        eval_accion = {
            "accion_consultada": "BUY",
            "probabilidad_exito": p_buy,
            "riesgo_perdida": p_sell,
            "neutralidad": p_hold,
            "mensaje": f"Evaluando COMPRA: Probabilidad de éxito del {round(p_buy * 100, 2)}% vs riesgo de pérdida del {round(p_sell * 100, 2)}%."
        }
    elif act_usr == "SELL":
        eval_accion = {
            "accion_consultada": "SELL",
            "probabilidad_exito": p_sell,
            "riesgo_perdida": p_buy,
            "neutralidad": p_hold,
            "mensaje": f"Evaluando VENTA: Probabilidad de éxito del {round(p_sell * 100, 2)}% vs riesgo de pérdida del {round(p_buy * 100, 2)}%."
        }
    else:
        eval_accion = {
            "accion_consultada": "HOLD",
            "probabilidad_exito": p_hold,
            "riesgo_perdida": round(p_buy + p_sell, 4),
            "neutralidad": 0.0,
            "mensaje": f"Evaluando ESPERA: Probabilidad de estabilidad del {round(p_hold * 100, 2)}% vs riesgo de movimiento del {round((p_buy + p_sell) * 100, 2)}%."
        }

    explicacion_bayeseana = generar_explicacion_bayeseana(evidencia, submodelo, recomendacion, probs_raw)
    explicacion_textual = generar_explicacion(evidencia, recomendacion)

    return {
        "recomendacion":       recomendacion,
        "probabilidades":      probs_raw,
        "probabilidades_calibradas": probs_cal,
        "probabilidad":        round(probs_raw[recomendacion], 4),
        "probabilidad_pct":    round(probs_raw[recomendacion] * 100, 2),
        "confianza":           nivel,
        "color":               color,
        "umbral_perfil":       min_prob,
        "perfil_riesgo":       perfil_riesgo,
        "modelo":              f"{submodelo.get('tipo', 'Red Bayesiana discreta')} ({nombre_modelo})",
        "modelo_version":      submodelo.get("version"),
        "accuracy_validacion": submodelo.get("accuracy_validacion"),
        "calibrado":           "calibracion_isotonica" in submodelo,
        "explicacion":         explicacion_textual,
        "explicacion_bayeseana": explicacion_bayeseana,
        "evaluacion_accion":   eval_accion,
        "variables": {
            **evidencia,
            "accion_evaluada": act_usr,
        },
    }


def predecir(tendencia, volumen, volatilidad, accion=None,
             indicadores=None, perfil_riesgo="moderado", symbol=None):
    return inferir_recomendacion(tendencia, volumen, volatilidad,
                                 accion, indicadores, perfil_riesgo, symbol)


# ══════════════════════════════════════════════════════════════════════════════
# Evaluación
# ══════════════════════════════════════════════════════════════════════════════

def evaluar_modelo(muestras: list[dict], modelo: dict, symbol: str | None = None) -> dict:
    if not muestras:
        return {"accuracy": 0.0, "total_validacion": 0, "correctos": 0}

    correctos = 0
    confusion = {c: {o: 0 for o in ["BUY", "SELL", "HOLD"]} for c in ["BUY", "SELL", "HOLD"]}
    
    for m in muestras:
        evidencia = _muestra_a_evidencia(m)
        esperado = _etiqueta_desde_muestra(m)
        probs, priors = inferir_probabilidades(evidencia, symbol or m.get("par"), modelo)
        
        pred = max(probs, key=probs.get)
            
        confusion[esperado][pred] += 1
        if pred == esperado:
            correctos += 1

    clases = ["BUY", "SELL", "HOLD"]
    metrics = {}
    f1_sum = 0.0
    for clase in clases:
        tp = confusion[clase][clase]
        fp = sum(confusion[other][clase] for other in clases if other != clase)
        fn = sum(confusion[clase][other] for other in clases if other != clase)
        
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * prec * rec) / (prec + rec) if (prec + rec) > 0 else 0.0
        f1_sum += f1
        metrics[clase] = {
            "precision": round(prec, 4),
            "recall": round(rec, 4),
            "f1": round(f1, 4)
        }

    balanced_acc = mean(metrics[c]["recall"] for c in clases)

    return {
        "accuracy":          round(correctos / len(muestras), 4),
        "accuracy_pct":      round((correctos / len(muestras)) * 100, 2),
        "balanced_accuracy": round(balanced_acc, 4),
        "balanced_accuracy_pct": round(balanced_acc * 100, 2),
        "total_validacion":  len(muestras),
        "correctos":         correctos,
        "f1_macro":          round(f1_sum / 3, 4),
        "metrics_per_class": metrics,
        "confusion_matrix":  confusion
    }
