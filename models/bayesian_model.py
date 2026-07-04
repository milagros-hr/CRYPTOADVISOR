"""
models/bayesian_model.py
Motor de Red Bayesiana discreta para CryptoAdvisor.

DIFERENCIA TEÓRICA CON UN CLASIFICADOR NAIVE BAYES SIMPLE:
──────────────────────────────────────────────────────────
1. Un modelo Naive Bayes clásico asume independencia condicional estricta entre 
   todas las variables de evidencia dadas la clase (Clase -> Indicador_i). Es decir:
       P(X1, X2, ..., Xn | R) = Prod_i P(Xi | R)
   Esto ignora las dependencias reales entre los indicadores financieros (por ejemplo, 
   la relación directa entre la volatilidad del mercado y el volumen negociado, o entre 
   la tendencia general y el oscilador RSI).

2. Esta Red Bayesiana implementa una estructura de Grafo Dirigido Acíclico (DAG) 
   donde existen dependencias cruzadas reales (Feature-to-Feature):
       P(R, X1, ..., Xn) = P(R) * Prod_i P(Xi | R, Parents_Features(Xi))
   Nuestros indicadores de tendencia (como RSI y MACD) tienen dependencias directas con 
   el nodo 'tendencia' principal del mercado, y los indicadores de rango (como Bollinger) 
   dependen del nodo 'volatilidad'.

3. El aprendizaje estructural por Mutual Information (MI) selecciona las características 
   más relevantes, y preserva automáticamente a los padres estructurales del DAG si alguno 
   de sus hijos es seleccionado, asegurando que las dependencias teóricas del dominio financiero 
   nunca se degraden hacia una topología Naive Bayes.
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

EXPERT_PRIORS = {
    "rsi_estado": {
        "BUY": {"sobreventa_extrema": 4.0, "sobreventa": 3.0, "neutral_bajo": 1.0, "neutral_alto": 0.0, "sobrecompra": 0.0, "sobrecompra_extrema": 0.0},
        "SELL": {"sobreventa_extrema": 0.0, "sobreventa": 0.0, "neutral_bajo": 0.0, "neutral_alto": 1.0, "sobrecompra": 3.0, "sobrecompra_extrema": 4.0},
        "HOLD": {"sobreventa_extrema": 0.5, "sobreventa": 1.0, "neutral_bajo": 3.0, "neutral_alto": 3.0, "sobrecompra": 1.0, "sobrecompra_extrema": 0.5}
    },
    "macd_estado": {
        "BUY": {"alcista": 4.0, "neutral": 1.0, "bajista": 0.1},
        "SELL": {"alcista": 0.1, "neutral": 1.0, "bajista": 4.0},
        "HOLD": {"alcista": 1.0, "neutral": 3.0, "bajista": 1.0}
    },
    "precio_vs_vwap": {
        "BUY": {"muy_bajo_vwap": 0.1, "bajo_vwap": 0.5, "neutral_vwap": 1.0, "sobre_vwap": 3.0, "muy_sobre_vwap": 4.0},
        "SELL": {"muy_bajo_vwap": 4.0, "bajo_vwap": 3.0, "neutral_vwap": 1.0, "sobre_vwap": 0.5, "muy_sobre_vwap": 0.1},
        "HOLD": {"muy_bajo_vwap": 1.0, "bajo_vwap": 2.0, "neutral_vwap": 3.0, "sobre_vwap": 2.0, "muy_sobre_vwap": 1.0}
    },
    "señal_momentum": {
        "BUY": {"bajista_extremo": 0.1, "bajista": 0.5, "neutral": 1.0, "alcista": 3.0, "alcista_extremo": 4.0},
        "SELL": {"bajista_extremo": 4.0, "bajista": 3.0, "neutral": 1.0, "alcista": 0.5, "alcista_extremo": 0.1},
        "HOLD": {"bajista_extremo": 1.0, "bajista": 2.0, "neutral": 3.0, "alcista": 2.0, "alcista_extremo": 1.0}
    },
    "bollinger_estado": {
        "BUY": {"bajo_banda_inferior": 4.0, "canal_inferior": 2.0, "canal_superior": 0.5, "sobre_banda_superior": 0.1},
        "SELL": {"bajo_banda_inferior": 0.1, "canal_inferior": 0.5, "canal_superior": 2.0, "sobre_banda_superior": 4.0},
        "HOLD": {"bajo_banda_inferior": 1.0, "canal_inferior": 3.0, "canal_superior": 3.0, "sobre_banda_superior": 1.0}
    }
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

# ══════════════════════════════════════════════════════════════════════════════
# Dependencias en el DAG para la Red Bayesiana
# ══════════════════════════════════════════════════════════════════════════════

DEPENDENCY_MAP = {
    "tendencia": [],
    "volatilidad": [],
    "adx_estado": ["volatilidad"],
    "volumen": ["volatilidad"],
    "rsi_estado": ["tendencia"],
    "macd_estado": ["tendencia"],
    "precio_vs_vwap": ["tendencia"],
    "bollinger_estado": ["volatilidad"],
    "señal_tendencia": ["tendencia"],
    "señal_momentum": ["tendencia"]
}

def obtener_padres_de(feat: str, selected_features: list[str]) -> list[str]:
    """Retorna la lista de variables padre de un feature en el DAG (incluyendo recomendacion)."""
    padres = ["recomendacion"]
    for p in DEPENDENCY_MAP.get(feat, []):
        if p in selected_features:
            padres.append(p)
    return padres

def construir_llave_padres(padres: list[str], sample: dict) -> str:
    """Construye una llave string que concatena los valores de los padres en la muestra."""
    valores = []
    for p in padres:
        if p == "recomendacion":
            val = sample.get("recomendacion") or "HOLD"
        else:
            val = sample.get(p)
            if val is None:
                val = _defecto_dominio(DOMINIOS[p])
        valores.append(str(val))
    return "|".join(valores)

def calcular_mutual_information(muestras: list[dict], features_candidatas: list[str]) -> dict[str, float]:
    """Calcula la Información Mutua I(X; Y) para cada feature candidato con respecto a la recomendación."""
    import math
    if not muestras:
        return {feat: 0.0 for feat in features_candidatas}
        
    n_samples = len(muestras)
    # 1. Calcular H(Y)
    conteo_y = Counter(m.get("recomendacion") for m in muestras)
    h_y = 0.0
    for val, count in conteo_y.items():
        p = count / n_samples
        if p > 0:
            h_y -= p * math.log2(p)
            
    mi_scores = {}
    for feat in features_candidatas:
        # 2. Calcular H(Y | X)
        count_x = Counter()
        count_xy = defaultdict(Counter)
        
        for m in muestras:
            x_val = m.get(feat)
            y_val = m.get("recomendacion")
            count_x[x_val] += 1
            count_xy[x_val][y_val] += 1
            
        h_y_dado_x = 0.0
        for x_val, count in count_x.items():
            p_x = count / n_samples
            h_y_x = 0.0
            for y_val, count_pair in count_xy[x_val].items():
                p_y_x = count_pair / count
                if p_y_x > 0:
                    h_y_x -= p_y_x * math.log2(p_y_x)
            h_y_dado_x += p_x * h_y_x
            
        mi_scores[feat] = max(0.0, h_y - h_y_dado_x)
        
    return mi_scores

# ══════════════════════════════════════════════════════════════════════════════
# Entrenamiento de la Red Bayesiana
# ══════════════════════════════════════════════════════════════════════════════

def entrenar_modelo(muestras: list[dict], alpha: float = 2.5, selected_features: list[str] | None = None) -> dict:
    """Entrena la Red Bayesiana calculando los conteos e infiriendo las CPTs con suavizado Laplace."""
    import itertools
    if not muestras:
        muestras = []
        
    simbolos_unicos = set(m.get("par") for m in muestras if m.get("par"))
    expert_weight = 35.0 if len(simbolos_unicos) == 1 else 0.0

    # 1. Filtrado de muestras a evidencia limpia
    muestras_ev = []
    for m in muestras:
        ev = _muestra_a_evidencia(m)
        ev["recomendacion"] = _etiqueta_desde_muestra(m)
        muestras_ev.append(ev)

    # 2. Selección automática de características si no se especifican
    cand_feats = [
        "tendencia", "volumen", "volatilidad", "rsi_estado", "macd_estado",
        "precio_vs_vwap", "bollinger_estado", "adx_estado", "señal_tendencia", "señal_momentum"
    ]
    mi_scores = calcular_mutual_information(muestras_ev, cand_feats)
    
    if selected_features is None:
        selected = [feat for feat, score in mi_scores.items() if score >= 0.002]
        if len(selected) < 4:
            sorted_feats = sorted(mi_scores.items(), key=lambda x: x[1], reverse=True)
            selected = [feat for feat, score in sorted_feats[:4]]
            
        # Asegurar que las variables padre estructurales (tendencia y volatilidad)
        # permanezcan si sus descendientes dependientes son seleccionados,
        # previniendo que se pierdan dependencias reales en el DAG.
        padres_requeridos = set()
        for feat in selected:
            for parent in DEPENDENCY_MAP.get(feat, []):
                if parent not in selected:
                    padres_requeridos.add(parent)
                    
        selected.extend(list(padres_requeridos))
        selected_features = [f for f in cand_feats if f in selected]

    # 3. Inicializar conteos
    clases_counts = {c: 0 for c in CLASES}
    cpts_counts = {}
    
    for feat in selected_features:
        cpts_counts[feat] = {}
        
    # 4. Llenar conteos desde las muestras
    for ev in muestras_ev:
        r = ev["recomendacion"]
        if r not in clases_counts:
            continue
        clases_counts[r] += 1
        
        for feat in selected_features:
            padres = obtener_padres_de(feat, selected_features)
            llave_padres = construir_llave_padres(padres, ev)
            
            if llave_padres not in cpts_counts[feat]:
                cpts_counts[feat][llave_padres] = {val: 0 for val in DOMINIOS[feat]}
                
            val_hijo = ev.get(feat)
            if val_hijo not in DOMINIOS[feat]:
                val_hijo = _defecto_dominio(DOMINIOS[feat])
                
            cpts_counts[feat][llave_padres][val_hijo] += 1

    # 5. Generar CPTs a partir de los conteos usando suavizado jerárquico (Back-off)
    priors = {}
    total_clases = sum(clases_counts.values())
    for c in CLASES:
        priors[c] = (clases_counts[c] + alpha) / (total_clases + alpha * len(CLASES))

    cpts = {}
    # Parámetro de pseudo-fuerza para el suavizado jerárquico
    k_backoff = 100.0
    
    for feat in selected_features:
        cpts[feat] = {}
        padres = obtener_padres_de(feat, selected_features)
        dominio_hijo = DOMINIOS[feat]
        
        # Asegurar probabilidad para todas las combinaciones de los padres
        dominios_padres = []
        for p in padres:
            if p == "recomendacion":
                dominios_padres.append(CLASES)
            else:
                dominios_padres.append(DOMINIOS[p])
                
        combinaciones = list(itertools.product(*dominios_padres))
        
        for comb in combinaciones:
            llave_comb = "|".join(str(v) for v in comb)
            clase = comb[0]
            
            counts_dict = cpts_counts[feat].get(llave_comb, {v: 0 for v in dominio_hijo})
            sum_counts = sum(counts_dict.values())
            
            # Obtener marginales agregando los contadores que comiencen con la clase
            marginal_dict = {v: 0 for v in dominio_hijo}
            for val in dominio_hijo:
                for key_p, val_counts in cpts_counts[feat].items():
                    if key_p.startswith(clase + "|") or key_p == clase:
                        marginal_dict[val] += val_counts.get(val, 0)
            sum_marginal = sum(marginal_dict.values())
            
            # Peso lambda para balancear condicional y marginal
            lamb = sum_counts / (sum_counts + k_backoff) if (sum_counts + k_backoff) > 0 else 0.0
            
            # Incorporar Prior Dirichlet del experto para suavizar casos out-of-distribution
            cpts[feat][llave_comb] = {}
            for val in dominio_hijo:
                p_cond = (counts_dict.get(val, 0) + alpha) / (sum_counts + alpha * len(dominio_hijo))
                p_marg = (marginal_dict.get(val, 0) + alpha) / (sum_marginal + alpha * len(dominio_hijo))
                p_data = lamb * p_cond + (1 - lamb) * p_marg
                
                if feat in EXPERT_PRIORS and clase in EXPERT_PRIORS[feat]:
                    prior_val = EXPERT_PRIORS[feat][clase].get(val, 0.0)
                    sum_prior = sum(EXPERT_PRIORS[feat][clase].values())
                    p_prior = prior_val / sum_prior if sum_prior > 0 else (1 / len(dominio_hijo))
                    
                    w = expert_weight / (sum_counts + expert_weight) if (sum_counts + expert_weight) > 0 else 0.0
                    cpts[feat][llave_comb][val] = (1 - w) * p_data + w * p_prior
                else:
                    cpts[feat][llave_comb][val] = p_data

    mi_formato = {feat: round(score, 6) for feat, score in mi_scores.items()}

    return {
        "tipo": "Red Bayesiana discreta",
        "version": datetime.now().strftime("%Y%m%d%H%M%S"),
        "fecha_entrenamiento": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "features": selected_features,
        "selected_features": selected_features,
        "dominios": DOMINIOS,
        "clases": CLASES,
        "priors": priors,
        "cpts": cpts,
        "clases_counts": clases_counts,
        "cpts_counts": cpts_counts,
        "mutual_information": mi_formato,
        "total_muestras": len(muestras),
        "alpha": alpha,
    }


def actualizar_modelo_incremental(muestra: dict, symbol: str | None = None, modelo: dict | None = None) -> dict:
    """
    Actualiza los conteos del submodelo correspondiente e incrementalmente recalcula las CPTs.
    """
    if modelo is None:
        modelo = cargar_modelo()
        
    symbol = (symbol or "").upper()
    submodelo, key_usada = obtener_submodelo(modelo, symbol)
    if not submodelo:
        modelo["global"] = entrenar_modelo([muestra])
        return modelo
        
    expert_weight = 35.0 if key_usada != "global" else 0.0
        
    ev = _muestra_a_evidencia(muestra)
    r = _etiqueta_desde_muestra(muestra)
    ev["recomendacion"] = r
    
    if r not in CLASES:
        return modelo
        
    # Inicializar contadores si no existen (retrocompatibilidad)
    if "clases_counts" not in submodelo:
        submodelo["clases_counts"] = {c: int(submodelo.get("total_muestras", 100) / len(CLASES)) for c in CLASES}
    if "cpts_counts" not in submodelo:
        submodelo["cpts_counts"] = {feat: {} for feat in submodelo.get("selected_features", submodelo.get("features", FEATURES))}
        
    clases_counts = submodelo["clases_counts"]
    cpts_counts = submodelo["cpts_counts"]
    selected_features = submodelo.get("selected_features", submodelo.get("features", FEATURES))
    alpha = submodelo.get("alpha", 2.5)
    
    # Incrementar contadores
    clases_counts[r] += 1
    
    for feat in selected_features:
        if feat not in cpts_counts:
            cpts_counts[feat] = {}
        padres = obtener_padres_de(feat, selected_features)
        llave_padres = construir_llave_padres(padres, ev)
        
        if llave_padres not in cpts_counts[feat]:
            cpts_counts[feat][llave_padres] = {val: 0 for val in DOMINIOS[feat]}
            
        val_hijo = ev.get(feat)
        if val_hijo not in DOMINIOS[feat]:
            val_hijo = _defecto_dominio(DOMINIOS[feat])
            
        cpts_counts[feat][llave_padres][val_hijo] += 1

    # Recalcular priors
    total_clases = sum(clases_counts.values())
    priors = {c: (clases_counts[c] + alpha) / (total_clases + alpha * len(CLASES)) for c in CLASES}
    submodelo["priors"] = priors
    
    # Recalcular CPTs para el caso modificado
    cpts = submodelo.get("cpts", {})
    for feat in selected_features:
        if feat not in cpts:
            cpts[feat] = {}
        padres = obtener_padres_de(feat, selected_features)
        llave_padres = construir_llave_padres(padres, ev)
        
        counts_dict = cpts_counts[feat].get(llave_padres, {v: 0 for v in DOMINIOS[feat]})
        sum_counts = sum(counts_dict.values())
        
        # Obtener marginales agregando los contadores que comiencen con la clase
        clase = llave_padres.split("|")[0]
        marginal_dict = {v: 0 for v in DOMINIOS[feat]}
        for val in DOMINIOS[feat]:
            for key_p, val_counts in cpts_counts[feat].items():
                if key_p.startswith(clase + "|") or key_p == clase:
                    marginal_dict[val] += val_counts.get(val, 0)
        sum_marginal = sum(marginal_dict.values())
        
        # Peso lambda para balancear condicional y marginal
        k_backoff = 100.0
        lamb = sum_counts / (sum_counts + k_backoff) if (sum_counts + k_backoff) > 0 else 0.0
        
        # Mezclar con el Prior Dirichlet del experto
        cpts[feat][llave_padres] = {}
        for val in DOMINIOS[feat]:
            p_cond = (counts_dict.get(val, 0) + alpha) / (sum_counts + alpha * len(DOMINIOS[feat]))
            p_marg = (marginal_dict.get(val, 0) + alpha) / (sum_marginal + alpha * len(DOMINIOS[feat]))
            p_data = lamb * p_cond + (1 - lamb) * p_marg
            
            if feat in EXPERT_PRIORS and clase in EXPERT_PRIORS[feat]:
                prior_val = EXPERT_PRIORS[feat][clase].get(val, 0.0)
                sum_prior = sum(EXPERT_PRIORS[feat][clase].values())
                p_prior = prior_val / sum_prior if sum_prior > 0 else (1 / len(DOMINIOS[feat]))
                
                w = expert_weight / (sum_counts + expert_weight) if (sum_counts + expert_weight) > 0 else 0.0
                cpts[feat][llave_padres][val] = (1 - w) * p_data + w * p_prior
            else:
                cpts[feat][llave_padres][val] = p_data
            
    submodelo["cpts"] = cpts
    submodelo["total_muestras"] = total_clases
    submodelo["fecha_entrenamiento"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    submodelo["version"] = datetime.now().strftime("%Y%m%d%H%M%S")
    
    if key_usada == "global":
        modelo["global"] = submodelo
    else:
        modelo[key_usada] = submodelo
        
    return modelo


# ══════════════════════════════════════════════════════════════════════════════
# Calibración empírica/isotónica
# ══════════════════════════════════════════════════════════════════════════════

N_BINS = 10

def _construir_tabla_calibracion(muestras_val: list[dict], modelo: dict) -> dict:
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
    if not tabla or clase not in tabla:
        return score
    b = min(int(score * N_BINS), N_BINS - 1)
    clase_tabla = tabla[clase]
    b_str = str(b)
    if b_str in clase_tabla:
        return clase_tabla[b_str]
    if b in clase_tabla:
        return clase_tabla[b]
    keys = sorted(clase_tabla.keys(), key=lambda k: abs(int(k) - b))
    if keys:
        return clase_tabla[keys[0]]
    return score


# ══════════════════════════════════════════════════════════════════════════════
# Carga, guardado y submodelos
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
    return {"global": entrenar_modelo(_cargar_muestras())}


def guardar_modelo(modelo: dict) -> None:
    _guardar_json(MODEL_PATH, modelo)


# ══════════════════════════════════════════════════════════════════════════════
# Inferencia probabilística exacta en el DAG
# ══════════════════════════════════════════════════════════════════════════════

def _inferir_scores_raw(evidencia: dict, submodelo: dict) -> dict:
    scores = {}
    priors = submodelo.get("priors", {})
    cpts = submodelo.get("cpts", {})
    selected_features = submodelo.get("selected_features", submodelo.get("features", FEATURES))
    
    for clase in CLASES:
        score = float(priors.get(clase, 1 / len(CLASES)))
        for feat in selected_features:
            val = evidencia.get(feat)
            if val is None:
                continue
                
            padres = obtener_padres_de(feat, selected_features)
            llave_padres_lista = []
            for p in padres:
                if p == "recomendacion":
                    llave_padres_lista.append(clase)
                else:
                    val_p = evidencia.get(p)
                    if val_p is None:
                        val_p = _defecto_dominio(DOMINIOS[p])
                    llave_padres_lista.append(val_p)
            llave_padres = "|".join(str(v) for v in llave_padres_lista)
            
            prob_cpt = (
                cpts.get(feat, {})
                .get(llave_padres, {})
                .get(val, 1 / max(len(DOMINIOS[feat]), 1))
            )
            score *= float(prob_cpt)
            
        scores[clase] = max(score, 1e-12)
    return scores


def inferir_probabilidades(evidencia: dict, symbol: str | None = None, modelo: dict | None = None) -> tuple[dict, dict]:
    modelo = modelo or cargar_modelo()
    submodelo, _ = obtener_submodelo(modelo, symbol)
    scores = _inferir_scores_raw(evidencia, submodelo)
    total = sum(scores.values())
    probs_raw = {c: round(scores[c] / total, 4) for c in CLASES}
    return probs_raw, submodelo.get("priors", {c: 1/len(CLASES) for c in CLASES})


def inferir_probabilidades_calibradas(evidencia: dict, symbol: str | None = None, modelo: dict | None = None) -> dict:
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
# Explicabilidad mediante Weight of Evidence (WoE)
# ══════════════════════════════════════════════════════════════════════════════

def generar_explicacion_bayeseana(evidencia: dict, submodelo: dict, recomendacion: str, probs_raw: dict) -> dict:
    import math
    cpts = submodelo.get("cpts", {})
    selected_features = submodelo.get("selected_features", submodelo.get("features", FEATURES))
    
    contribuciones_detalladas = []
    buy_list = []
    sell_list = []
    hold_list = []
    
    for feat in selected_features:
        val = evidencia.get(feat)
        if val is None:
            continue
            
        padres = obtener_padres_de(feat, selected_features)
        probs_clases = {}
        for c in CLASES:
            llave_padres_lista = []
            for p in padres:
                if p == "recomendacion":
                    llave_padres_lista.append(c)
                else:
                    val_p = evidencia.get(p)
                    if val_p is None:
                        val_p = _defecto_dominio(DOMINIOS[p])
                    llave_padres_lista.append(val_p)
            llave_padres = "|".join(str(v) for v in llave_padres_lista)
            
            prob_cpt = (
                cpts.get(feat, {})
                .get(llave_padres, {})
                .get(val, 0.0)
            )
            if prob_cpt == 0.0:
                prob_cpt = 1 / max(len(DOMINIOS[feat]), 1)
            probs_clases[c] = float(prob_cpt)
            
        prob_media = sum(probs_clases.values()) / len(CLASES)
        
        # Calcular WoE para cada clase individualmente
        woe_buy = math.log2((probs_clases["BUY"] + 1e-6) / (prob_media + 1e-6))
        woe_sell = math.log2((probs_clases["SELL"] + 1e-6) / (prob_media + 1e-6))
        woe_hold = math.log2((probs_clases["HOLD"] + 1e-6) / (prob_media + 1e-6))
        
        # Clase favorecida es la que obtiene el mayor peso de evidencia
        clases_woe = {"BUY": woe_buy, "SELL": woe_sell, "HOLD": woe_hold}
        clase_favorecida = max(clases_woe, key=clases_woe.get)
        peso_evidencia = clases_woe[clase_favorecida]
        
        # Explicación en lenguaje natural
        if clase_favorecida == "BUY":
            explicacion_txt = f"El estado '{val}' de la variable '{feat}' incrementa la probabilidad de compra (BUY) con un peso de evidencia de {peso_evidencia:+.2f} bits, sugiriendo un escenario alcista o sobreventa."
        elif clase_favorecida == "SELL":
            explicacion_txt = f"El estado '{val}' de la variable '{feat}' incrementa la probabilidad de venta (SELL) con un peso de evidencia de {peso_evidencia:+.2f} bits, sugiriendo un escenario bajista o sobrecompra."
        else:
            explicacion_txt = f"El estado '{val}' de la variable '{feat}' favorece la espera (HOLD) con un peso de evidencia de {peso_evidencia:+.2f} bits, indicando neutralidad o falta de dirección clara."
            
        contribuciones_detalladas.append({
            "variable_observada": feat,
            "valor_observado": val,
            "clase_favorecida": clase_favorecida,
            "peso_evidencia": round(peso_evidencia, 4),
            "explicacion": explicacion_txt
        })
        
        # Llenar las listas de compatibilidad visual
        if woe_buy > 0.05:
            buy_list.append(f"{feat}={val} (+{woe_buy:.2f} bits)")
        if woe_sell > 0.05:
            sell_list.append(f"{feat}={val} (+{woe_sell:.2f} bits)")
        if woe_hold > 0.05:
            hold_list.append(f"{feat}={val} (+{woe_hold:.2f} bits)")
            
    # Encontrar la variable observada que tiene el mayor peso de evidencia a favor de la recomendación final
    mejor_woe_recom = -99.0
    mejor_feat_recom = None
    mejor_val_recom = None
    
    for feat in selected_features:
        val = evidencia.get(feat)
        if val is None:
            continue
        padres = obtener_padres_de(feat, selected_features)
        probs_clases = {}
        for c in CLASES:
            llave_padres_lista = []
            for p in padres:
                if p == "recomendacion":
                    llave_padres_lista.append(c)
                else:
                    val_p = evidencia.get(p)
                    if val_p is None:
                        val_p = _defecto_dominio(DOMINIOS[p])
                    llave_padres_lista.append(val_p)
            llave_padres = "|".join(str(v) for v in llave_padres_lista)
            
            prob_cpt = (
                cpts.get(feat, {})
                .get(llave_padres, {})
                .get(val, 0.0)
            )
            if prob_cpt == 0.0:
                prob_cpt = 1 / max(len(DOMINIOS[feat]), 1)
            probs_clases[c] = float(prob_cpt)
            
        prob_media = sum(probs_clases.values()) / len(CLASES)
        woe_rec = math.log2((probs_clases[recomendacion] + 1e-6) / (prob_media + 1e-6))
        if woe_rec > mejor_woe_recom:
            mejor_woe_recom = woe_rec
            mejor_feat_recom = feat
            mejor_val_recom = val
            
    if mejor_feat_recom is not None and mejor_woe_recom > 0.0:
        if recomendacion == "BUY":
            razon_principal = f"Inferencia alcista (BUY) impulsada principalmente por '{mejor_feat_recom}={mejor_val_recom}' que aporta {mejor_woe_recom:+.2f} bits a favor."
        elif recomendacion == "SELL":
            razon_principal = f"Inferencia bajista (SELL) impulsada principalmente por '{mejor_feat_recom}={mejor_val_recom}' que aporta {mejor_woe_recom:+.2f} bits a favor."
        else:
            razon_principal = f"Inferencia de cautela (HOLD) impulsada principalmente por '{mejor_feat_recom}={mejor_val_recom}' que aporta {mejor_woe_recom:+.2f} bits a favor."
    else:
        razon_principal = f"Inferencia de {recomendacion} basada en priors de probabilidad del modelo."
        
    return {
        "variables_observadas": evidencia,
        "contribuciones_detalladas": contribuciones_detalladas,
        "evidencias_favor_buy": buy_list,
        "evidencias_favor_sell": sell_list,
        "evidencias_favor_hold": hold_list,
        "razon_principal": razon_principal
    }


def generar_explicacion(evidencia: dict, recomendacion: str) -> str:
    factores = []
    for k, v in evidencia.items():
        if k in ("tendencia", "volumen", "volatilidad", "rsi_estado", "macd_estado"):
            factores.append(f"{k}={v}")
    
    # Explicación amigable adicional para usuarios no técnicos
    if recomendacion == "BUY":
        amigable = "El sistema recomienda COMPRAR (BUY) porque la mayoría de los indicadores del mercado sugieren que el precio actual está en zona de sobreventa o muestra un impulso alcista que favorece el inicio de una tendencia alcista a corto plazo."
        tecnica = f"Detalle técnico: Se observa un alineamiento positivo del modelo bayesiano con el sesgo de: {', '.join(factores)}."
    elif recomendacion == "SELL":
        amigable = "El sistema recomienda VENDER (SELL) debido a que los indicadores técnicos sugieren condiciones de sobrecompra o una presión bajista fuerte, lo que incrementa el riesgo de caídas en el precio y favorece la toma de ganancias."
        tecnica = f"Detalle técnico: Se observa un alineamiento negativo del modelo bayesiano con el sesgo de: {', '.join(factores)}."
    else:
        amigable = "El sistema recomienda ESPERAR (HOLD) porque las señales actuales del mercado son mixtas, la tendencia no está definida, o se registra una volatilidad riesgosa donde la confianza matemática no es suficiente para recomendar compra o venta."
        tecnica = f"Detalle técnico: Se recomienda prudencia con base en el sesgo de cautela de: {', '.join(factores)}."
        
    return f"{amigable}\n\n{tecnica}"


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
    
    # 2. Decisión basada en comparación con HOLD escalada por perfil (Sin reglas hardcodeadas)
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
# Evaluación exhaustiva del rendimiento probabilístico y de calibración
# ══════════════════════════════════════════════════════════════════════════════

def evaluar_modelo(muestras: list[dict], modelo: dict, symbol: str | None = None) -> dict:
    if not muestras:
        return {"accuracy": 0.0, "total_validacion": 0, "correctos": 0}

    correctos = 0
    confusion = {c: {o: 0 for o in CLASES} for c in CLASES}
    
    y_true_all = []
    y_pred_probs_cal = []
    
    for m in muestras:
        evidencia = _muestra_a_evidencia(m)
        esperado = _etiqueta_desde_muestra(m)
        
        # Inferencia de probabilidades raw para la predicción de la clase
        probs_raw, _ = inferir_probabilidades(evidencia, symbol or m.get("par"), modelo)
        pred = max(probs_raw, key=probs_raw.get)
        
        # Probabilidades calibradas para Brier y ECE
        probs_cal = inferir_probabilidades_calibradas(evidencia, symbol or m.get("par"), modelo)
            
        confusion[esperado][pred] += 1
        if pred == esperado:
            correctos += 1
            
        y_true_all.append(esperado)
        y_pred_probs_cal.append(probs_cal)

    total_muestras = len(muestras)
    accuracy = correctos / total_muestras
    
    metrics = {}
    f1_sum = 0.0
    prec_sum = 0.0
    rec_sum = 0.0
    
    for clase in CLASES:
        tp = confusion[clase][clase]
        fp = sum(confusion[other][clase] for other in CLASES if other != clase)
        fn = sum(confusion[clase][other] for other in CLASES if other != clase)
        
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * prec * rec) / (prec + rec) if (prec + rec) > 0 else 0.0
        
        f1_sum += f1
        prec_sum += prec
        rec_sum += rec
        
        metrics[clase] = {
            "precision": round(prec, 4),
            "recall": round(rec, 4),
            "f1": round(f1, 4)
        }

    f1_macro = f1_sum / len(CLASES)
    precision_macro = prec_sum / len(CLASES)
    recall_macro = rec_sum / len(CLASES)
    balanced_acc = recall_macro

    # Brier Score (sobre probabilidades calibradas)
    brier_score = 0.0
    for y_true, probs in zip(y_true_all, y_pred_probs_cal):
        for c in CLASES:
            p = probs.get(c, 0.0)
            y = 1.0 if y_true == c else 0.0
            brier_score += (p - y) ** 2
    brier_score /= total_muestras
    brier_score = round(brier_score, 6)

    # Expected Calibration Error (ECE)
    n_bins = 10
    bins = []
    for idx in range(n_bins):
        bins.append({
            "min": idx / n_bins,
            "max": (idx + 1) / n_bins,
            "label": f"{int(idx*10)}-{int((idx+1)*10)}%",
            "correct": 0,
            "total": 0,
            "conf_sum": 0.0
        })
        
    for y_true, probs in zip(y_true_all, y_pred_probs_cal):
        pred_c = max(probs, key=probs.get)
        confianza = probs[pred_c]
        is_correct = (pred_c == y_true)
        
        for b in bins:
            if b["min"] <= confianza < b["max"] or (b["max"] == 1.0 and confianza == 1.0):
                b["total"] += 1
                b["conf_sum"] += confianza
                if is_correct:
                    b["correct"] += 1
                break
                
    ece = 0.0
    calibration_curve = []
    for b in bins:
        if b["total"] > 0:
            avg_conf = b["conf_sum"] / b["total"]
            actual_acc = b["correct"] / b["total"]
            ece += (b["total"] / total_muestras) * abs(actual_acc - avg_conf)
            calibration_curve.append({
                "intervalo": b["label"],
                "total": b["total"],
                "confianza_promedio": round(avg_conf, 4),
                "precision_real": round(actual_acc, 4)
            })
        else:
            calibration_curve.append({
                "intervalo": b["label"],
                "total": 0,
                "confianza_promedio": None,
                "precision_real": None
            })

    return {
        "accuracy":                  round(accuracy, 4),
        "accuracy_pct":              round(accuracy * 100, 2),
        "balanced_accuracy":         round(balanced_acc, 4),
        "balanced_accuracy_pct":     round(balanced_acc * 100, 2),
        "precision_macro":           round(precision_macro, 4),
        "recall_macro":              round(recall_macro, 4),
        "f1_macro":                  round(f1_macro, 4),
        "f1_macro_pct":              round(f1_macro * 100, 2),
        "brier_score":               brier_score,
        "ece":                       round(ece, 4),
        "ece_pct":                   round(ece * 100, 2),
        "calibration_curve":         calibration_curve,
        "total_validacion":          total_muestras,
        "correctos":                 correctos,
        "metrics_per_class":         metrics,
        "confusion_matrix":          confusion
    }
