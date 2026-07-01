"""
services/training_service.py
Reentrenamiento, selección automática de hiperparámetros (Grid Search),
validación temporal (Time Series Cross Validation) y validación fuera de
muestra (OOS) de la Red Bayesiana en CryptoAdvisor.

Mejoras aplicadas:
──────────────────
• 10 pares de trading con histórico multi-timeframe (1d×1000 + 4h×500).
• Etiquetado de régimen de mercado (alcista/bajista/lateral) por segmento.
• Holdout OOS real: el 20% más antiguo del timeline se reserva antes del
  Grid Search y nunca se toca durante el entrenamiento ni el CV.
• Señales sintéticas (señal_tendencia, señal_momentum) alineadas con el
  modelo bayesiano reducido.
"""

import json
import math
import os
import random
from collections import Counter
from datetime import datetime
from statistics import mean, pstdev

from models import bayesian_model
from services.market_service import obtener_klines

TRAINING_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "training_data.json")

# ── Pares y configuración de descarga ──────────────────────────────────────
# 10 pares cubre BTC dominance, altcoins de alta liquidez y pares USDT/BTC
# distintos para capturar diferentes regímenes de correlación.
PARES_PRINCIPALES = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT",
    "ADAUSDT", "XRPUSDT", "DOGEUSDT", "AVAXUSDT",
    "LTCUSDT", "DOTUSDT",
]
# Configuración de descarga: diario largo + 4h para capturar múltiples regímenes
DESCARGA_CONFIG = [
    {"interval": "1d", "limit": 1000},   # ~2.7 años de historia diaria
    {"interval": "4h", "limit": 500},    # ~83 días de velas 4h
]


def DESCARGAR_CONFIG_SAFE():
    """Generador que itera sobre la configuración de descarga definida arriba."""
    yield from DESCARGA_CONFIG



def precalcular_evidencia_series(velas: list[dict]) -> list[dict]:
    """
    Precalcula en tiempo lineal O(N) todos los indicadores y estados discretizados
    para toda la serie de velas, incluyendo los nuevos 12 indicadores de evidencia.
    """
    n = len(velas)
    closes = [v["close"] for v in velas]
    volumes = [v["quote_volume"] for v in velas]
    
    # Retornos logarítmicos
    log_returns = [0.0] * n
    for i in range(1, n):
        if closes[i-1] > 0:
            log_returns[i] = math.log(closes[i] / closes[i-1])
            
    # SMA 50
    sma50 = [0.0] * n
    for i in range(n):
        if i >= 49:
            sma50[i] = mean(closes[i-49:i+1])
        else:
            sma50[i] = mean(closes[:i+1])
            
    # EMA 20
    ema20 = [0.0] * n
    ema20[0] = closes[0]
    alpha_20 = 2 / (20 + 1)
    for i in range(1, n):
        ema20[i] = closes[i] * alpha_20 + ema20[i-1] * (1 - alpha_20)
        
    # EMA 12 y 26 para MACD
    ema12 = [0.0] * n
    ema12[0] = closes[0]
    alpha_12 = 2 / (12 + 1)
    for i in range(1, n):
        ema12[i] = closes[i] * alpha_12 + ema12[i-1] * (1 - alpha_12)
        
    ema26 = [0.0] * n
    ema26[0] = closes[0]
    alpha_26 = 2 / (26 + 1)
    for i in range(1, n):
        ema26[i] = closes[i] * alpha_26 + ema26[i-1] * (1 - alpha_26)
        
    # MACD e Histograma
    macd_line = [0.0] * n
    for i in range(n):
        macd_line[i] = ema12[i] - ema26[i]
        
    macd_signal = [0.0] * n
    macd_signal[0] = macd_line[0]
    alpha_9 = 2 / (9 + 1)
    for i in range(1, n):
        macd_signal[i] = macd_line[i] * alpha_9 + macd_signal[i-1] * (1 - alpha_9)
        
    macd_histogram = [macd_line[i] - macd_signal[i] for i in range(n)]
    
    # RSI 14
    rsi = [50.0] * n
    gains = [0.0] * (n - 1)
    losses = [0.0] * (n - 1)
    for i in range(1, n):
        diff = closes[i] - closes[i-1]
        gains[i-1] = max(diff, 0)
        losses[i-1] = abs(min(diff, 0))
        
    for i in range(14, n):
        avg_gain = mean(gains[i-14:i])
        avg_loss = mean(losses[i-14:i])
        if avg_loss == 0:
            rsi[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi[i] = 100.0 - (100.0 / (1.0 + rs))
            
    # Bandas de Bollinger (20, 2)
    bollinger_upper = [0.0] * n
    bollinger_lower = [0.0] * n
    for i in range(n):
        window = closes[max(0, i-19):i+1]
        mid = mean(window)
        sd = pstdev(window) if len(window) > 1 else 0.0
        bollinger_upper[i] = mid + 2.0 * sd
        bollinger_lower[i] = mid - 2.0 * sd
        
    # VWAP (Ventana móvil de 20 periodos)
    vwap = [0.0] * n
    for i in range(n):
        window_velas = velas[max(0, i-19):i+1]
        pv = sum((v["high"] + v["low"] + v["close"]) / 3 * v["volume"] for v in window_velas)
        vol = sum(v["volume"] for v in window_velas)
        vwap[i] = pv / vol if vol > 0 else closes[i]

    # ADX (Average Directional Index)
    tr = [0.0] * n
    p_dm = [0.0] * n
    m_dm = [0.0] * n
    for i in range(1, n):
        h, l = velas[i]["high"], velas[i]["low"]
        ph, pl = velas[i-1]["high"], velas[i-1]["low"]
        pc = velas[i-1]["close"]
        
        tr[i] = max(h - l, abs(h - pc), abs(l - pc))
        
        up = h - ph
        down = pl - l
        
        if up > down and up > 0:
            p_dm[i] = up
        if down > up and down > 0:
            m_dm[i] = down
            
    str_val = [0.0] * n
    sp_dm = [0.0] * n
    sm_dm = [0.0] * n
    if n >= 15:
        str_val[14] = sum(tr[1:15])
        sp_dm[14] = sum(p_dm[1:15])
        sm_dm[14] = sum(m_dm[1:15])
        for i in range(15, n):
            str_val[i] = str_val[i-1] - (str_val[i-1]/14) + tr[i]
            sp_dm[i] = sp_dm[i-1] - (sp_dm[i-1]/14) + p_dm[i]
            sm_dm[i] = sm_dm[i-1] - (sm_dm[i-1]/14) + m_dm[i]
            
    dx = [0.0] * n
    for i in range(14, n):
        sv = str_val[i]
        if sv > 0:
            p_di = (sp_dm[i] / sv) * 100
            m_di = (sm_dm[i] / sv) * 100
            di_diff = abs(p_di - m_di)
            di_sum = p_di + m_di
            dx[i] = (di_diff / di_sum * 100) if di_sum > 0 else 0.0
            
    adx = [15.0] * n
    for i in range(27, n):
        adx[i] = mean(dx[i-13:i+1])

    results = []
    for i in range(n):
        precio = closes[i]
        em20 = ema20[i]
        sm50 = sma50[i]
        macd_hist = macd_histogram[i]

        # Tendencia primaria
        if precio > em20 > sm50 and macd_hist > 0:
            tendencia = "alcista"
        elif precio < em20 < sm50 and macd_hist < 0:
            tendencia = "bajista"
        else:
            tendencia = "lateral"
        # Volumen relativo (RVOL)
        if i >= 19:
            vols = volumes[i-19:i+1]
            v_sma = mean(vols)
            rvol = volumes[i] / v_sma if v_sma > 0 else 1.0
        else:
            rvol = 1.0
        volumen = bayesian_model.discretizar_volumen_relativo(rvol)

        # Volatilidad
        if i >= 9:
            rets = log_returns[max(0, i-49):i+1]
            sd = pstdev(rets) if len(rets) >= 2 else 0.0
        else:
            sd = 0.01
        volatilidad = bayesian_model.discretizar_volatilidad(sd)

        # ADX
        adx_val = adx[i]
        adx_estado = bayesian_model.discretizar_adx(adx_val)

        # Pendientes individuales (se combinarán en señal_tendencia)
        ema_slope = (ema20[i] - ema20[i-1]) / ema20[i-1] if i >= 1 and ema20[i-1] > 0 else 0.0
        pendiente_ema = "alcista" if ema_slope > 0.0005 else ("bajista" if ema_slope < -0.0005 else "lateral")

        sma_slope = (sma50[i] - sma50[i-1]) / sma50[i-1] if i >= 1 and sma50[i-1] > 0 else 0.0
        pendiente_sma = "alcista" if sma_slope > 0.0002 else ("bajista" if sma_slope < -0.0002 else "lateral")

        # Señal sintética de tendencia (voto mayoría: pendiente_ema + pendiente_sma)
        votos_tend = Counter([pendiente_ema, pendiente_sma])
        señal_tendencia = votos_tend.most_common(1)[0][0]

        # Retorno y momentum (se combinarán en señal_momentum)
        ret_pct = (closes[i] - closes[i-1]) / closes[i-1] if i >= 1 and closes[i-1] > 0 else 0.0
        retorno_estado = "positivo" if ret_pct > 0.005 else ("negativo" if ret_pct < -0.005 else "neutral")

        momentum_val = (closes[i] - closes[i-10]) / closes[i-10] if i >= 10 and closes[i-10] > 0 else 0.0
        momentum_estado = "alto" if momentum_val > 0.02 else ("bajo" if momentum_val < -0.02 else "neutral")

        # Señal sintética de momentum (discretización fina directa del valor)
        señal_momentum = bayesian_model.discretizar_señal_momentum(momentum_val)

        # RSI, MACD, VWAP, Bollinger
        rsi_val = rsi[i]
        rsi_estado = bayesian_model.discretizar_rsi(rsi_val)
        macd_estado = "alcista" if macd_hist > 0 else ("bajista" if macd_hist < 0 else "neutral")
        
        precio_vs_vwap = bayesian_model.discretizar_precio_vs_vwap(precio, vwap[i])
        
        boll_mid = (bollinger_upper[i] + bollinger_lower[i]) / 2.0
        bollinger_estado = bayesian_model.discretizar_bollinger(precio, bollinger_lower[i], boll_mid, bollinger_upper[i])
        # Régimen global del segmento (últimas 20 velas) para separar en grid search
        if i >= 19:
            window_c = closes[i-19:i+1]
            ret_window = (window_c[-1] - window_c[0]) / window_c[0] if window_c[0] > 0 else 0.0
            sd_window = pstdev([math.log(window_c[j] / window_c[j-1])
                                 for j in range(1, len(window_c))
                                 if window_c[j-1] > 0]) if len(window_c) > 2 else 0.0
            if ret_window > 0.05:
                regimen = "alcista"
            elif ret_window < -0.05:
                regimen = "bajista"
            else:
                regimen = "lateral"
        else:
            regimen = "lateral"

        results.append({
            "precio_actual":    precio,
            "tendencia":        tendencia,
            "volumen":          volumen,
            "volatilidad":      volatilidad,
            "rsi_estado":       rsi_estado,
            "macd_estado":      macd_estado,
            "precio_vs_vwap":   precio_vs_vwap,
            "bollinger_estado": bollinger_estado,
            "adx_estado":       adx_estado,
            # Señales sintéticas (modelo reducido)
            "señal_tendencia":  señal_tendencia,
            "señal_momentum":   señal_momentum,
            # Campos originales: conservados para compatibilidad con muestras antiguas
            "pendiente_ema":    pendiente_ema,
            "pendiente_sma":    pendiente_sma,
            "retorno_estado":   retorno_estado,
            "momentum_estado":  momentum_estado,
            # Metadatos de régimen (no entran en el modelo, solo para análisis)
            "regimen":          regimen,
        })
    return results


def generar_dataset(N: int, threshold: float, klines_dict: dict,
                    regimenes_requeridos: list[str] | None = None) -> list[dict]:
    """
    Genera muestras etiquetadas con horizonte N y umbral dado.

    Args:
        N: Horizonte de predicción en velas.
        threshold: Umbral de retorno para clasificar BUY/SELL.
        klines_dict: Diccionario {par: lista_de_velas}.
        regimenes_requeridos: Si se especifica, solo incluye muestras cuyo
            régimen esté en la lista (ej. ["alcista", "bajista"]).  Útil para
            entrenar modelos especializados por régimen o para stratificación.
    """
    muestras = []
    for par, velas in klines_dict.items():
        n_velas = len(velas)
        if n_velas < 100:
            continue

        estados = precalcular_evidencia_series(velas)
        for i in range(50, n_velas - N):
            est = estados[i]

            # Filtrar por régimen si se solicita
            if regimenes_requeridos and est.get("regimen") not in regimenes_requeridos:
                continue

            precio = est["precio_actual"]
            precio_futuro = velas[i + N]["close"]
            retorno = (precio_futuro - precio) / precio

            if retorno >= threshold:
                recomendacion = "BUY"
            elif retorno <= -threshold:
                recomendacion = "SELL"
            else:
                recomendacion = "HOLD"

            muestras.append({
                "open_time":        velas[i]["open_time"],
                "tendencia":        est["tendencia"],
                "volumen":          est["volumen"],
                "volatilidad":      est["volatilidad"],
                "rsi_estado":       est["rsi_estado"],
                "macd_estado":      est["macd_estado"],
                "precio_vs_vwap":   est["precio_vs_vwap"],
                "bollinger_estado": est["bollinger_estado"],
                "adx_estado":       est["adx_estado"],
                # Señales sintéticas (modelo reducido)
                "señal_tendencia":  est["señal_tendencia"],
                "señal_momentum":   est["señal_momentum"],
                # Campos originales (compatibilidad)
                "pendiente_ema":    est["pendiente_ema"],
                "pendiente_sma":    est["pendiente_sma"],
                "retorno_estado":   est["retorno_estado"],
                "momentum_estado":  est["momentum_estado"],
                "recomendacion":    recomendacion,
                "regimen":          est.get("regimen", "lateral"),
                "par":              par,
            })
    # Ordenar por open_time cronológicamente
    muestras = sorted(muestras, key=lambda x: x.get("open_time", 0))
    return muestras


def evaluar_modelo_cv(muestras: list[dict], ratio: float) -> dict:
    """
    Realiza Time Series Cross Validation (3 splits temporales) respetando el orden temporal.
    Retorna el promedio de F1 Macro, Recall BUY, Recall SELL, Accuracy y Baseline.
    """
    M = len(muestras)
    if M < 30:
        return {"f1_macro": 0.0, "buy_recall": 0.0, "sell_recall": 0.0, "acc": 0.0, "baseline": 0.0}
        
    # Splits: 50% inicial, 65% inicial, 80% inicial
    splits = [
        (0, int(M * 0.5), int(M * 0.5), int(M * 0.65)),
        (0, int(M * 0.65), int(M * 0.65), int(M * 0.8)),
        (0, int(M * 0.8), int(M * 0.8), M)
    ]
    
    accuracies = []
    baselines = []
    f1_macros = []
    f1_minorities = []
    rec_buys = []
    rec_sells = []
    
    clases_list = ["BUY", "SELL", "HOLD"]
    
    for train_start, train_end, val_start, val_end in splits:
        train = muestras[train_start:train_end]
        val = muestras[val_start:val_end]
        if not train or not val:
            continue
            
        # Balanceo en entrenamiento por undersampling de HOLD
        buys = [m for m in train if m["recomendacion"] == "BUY"]
        sells = [m for m in train if m["recomendacion"] == "SELL"]
        holds = [m for m in train if m["recomendacion"] == "HOLD"]
        
        target_holds = int(ratio * max(len(buys), len(sells)))
        random.Random(42).shuffle(holds)
        if len(holds) > target_holds:
            holds = holds[:target_holds]
        train_balanced = buys + sells + holds
        
        # Entrenar modelo temporal
        modelo_tmp = bayesian_model.entrenar_modelo(train_balanced)
        
        # Validar modelo temporal
        correctos = 0
        conf_matrix = {c: {cc: 0 for cc in clases_list} for c in clases_list}
        
        for m in val:
            evidencia = bayesian_model._muestra_a_evidencia(m)
            probs, priors = bayesian_model.inferir_probabilidades(
                evidencia, m.get("par"), modelo_tmp
            )
            
            pred = max(probs, key=probs.get)
            true_lbl = m["recomendacion"]
            conf_matrix[true_lbl][pred] += 1
            if pred == true_lbl:
                correctos += 1
                
        acc = correctos / len(val) if val else 0.0
        accuracies.append(acc)
        
        # Baseline mayoritaria
        val_labels = [m["recomendacion"] for m in val]
        counts_val = Counter(val_labels)
        clase_may = counts_val.most_common(1)[0][1] if counts_val else 0
        baselines.append(clase_may / len(val) if val else 0.0)
        
        # F1s y Recalls
        f1s_fold = []
        recalls_fold = {}
        for clase in clases_list:
            tp = conf_matrix[clase][clase]
            fp = sum(conf_matrix[other][clase] for other in clases_list if other != clase)
            fn = sum(conf_matrix[clase][other] for other in clases_list if other != clase)
            
            prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            f1 = (2 * prec * rec) / (prec + rec) if (prec + rec) > 0 else 0.0
            
            f1s_fold.append(f1)
            recalls_fold[clase] = rec
            
        f1_macros.append(mean(f1s_fold))
        f1_minorities.append((f1s_fold[0] + f1s_fold[1]) / 2) # F1 average of BUY and SELL
        rec_buys.append(recalls_fold["BUY"])
        rec_sells.append(recalls_fold["SELL"])
        
    return {
        "acc": mean(accuracies) if accuracies else 0.0,
        "baseline": mean(baselines) if baselines else 0.0,
        "f1_macro": mean(f1_macros) if f1_macros else 0.0,
        "f1_minority": mean(f1_minorities) if f1_minorities else 0.0,
        "buy_recall": mean(rec_buys) if rec_buys else 0.0,
        "sell_recall": mean(rec_sells) if rec_sells else 0.0,
    }


def reentrenar_modelo():
    """
    Descarga datos reales de Binance (10 pares, multi-timeframe), realiza
    Grid Search + Time Series CV, y reserva un holdout OOS del período más
    antiguo para validación verdadera fuera de muestra.

    Flujo:
    1. Descarga 10 pares × (1d×1000 + 4h×500).
    2. Separa el 20% cronológicamente más antiguo de cada serie como OOS
       (jamás se usa en entrenamiento ni en CV).
    3. Grid Search sobre N, threshold y ratio en el 80% restante.
    4. Entrena modelo final sobre 80% de entrenamiento con calibración isotónica.
    5. Evalúa en OOS y en el último 20% del período de entrenamiento.
    6. Aplica guards de despliegue y persiste o rechaza.
    """
    klines_dict_train = {}   # 80% más reciente de cada par (para CV + entrenamiento)
    klines_dict_oos = {}     # 20% más antiguo de cada par (holdout real)

    print("[Training] Descargando histórico Binance (10 pares, multi-timeframe)...")
    for par in PARES_PRINCIPALES:
        velas_par = []
        for cfg in DESCARGAR_CONFIG_SAFE():
            try:
                velas = obtener_klines(par, interval=cfg["interval"], limit=cfg["limit"])
                if len(velas) >= 100:
                    # Ordenar cronológicamente (más antiguo primero)
                    velas_par.extend(velas)
            except Exception as e:
                print(f"[Training] Error descargando {par} {cfg['interval']}: {e}")

        if len(velas_par) < 100:
            print(f"[Training] {par}: datos insuficientes, omitido.")
            continue

        # Deduplicar por open_time y reordenar
        seen = {}
        for v in velas_par:
            seen[v["open_time"]] = v
        velas_par = sorted(seen.values(), key=lambda v: v["open_time"])

        # Separar OOS: 20% más antiguo (período histórico distinto)
        n_oos = max(1, int(len(velas_par) * 0.20))
        oos_velas = velas_par[:n_oos]
        train_velas = velas_par[n_oos:]

        if len(train_velas) >= 100:
            klines_dict_train[par] = train_velas
        if len(oos_velas) >= 50:
            klines_dict_oos[par] = oos_velas

    if not klines_dict_train:
        return {
            "ok": False,
            "mensaje": "No se pudo obtener datos de Binance para ningún par.",
            "datos": {}
        }

    n_pares = len(klines_dict_train)
    print(f"[Training] Pares disponibles para entrenamiento: {n_pares}/{len(PARES_PRINCIPALES)}")
            
    # ── Grid Search ────────────────────────────────────────────────────────
    N_list = [3, 5]
    threshold_list = [0.012, 0.015]
    ratio_list = [1.0, 1.2]

    best_config = None
    best_score_f1 = -1.0
    best_recall_sum = -1.0

    print("[Training] Iniciando Grid Search y Time Series CV...")
    for N in N_list:
        for th in threshold_list:
            muestras_temp = generar_dataset(N, th, klines_dict_train)
            if not muestras_temp:
                continue

            for ratio in ratio_list:
                res_cv = evaluar_modelo_cv(muestras_temp, ratio)
                
                # Excluir configuraciones degeneradas que no predicen BUY o SELL
                if res_cv["buy_recall"] < 0.05 or res_cv["sell_recall"] < 0.05:
                    continue
                    
                f1_min = res_cv["f1_minority"]
                rec_sum = res_cv["buy_recall"] + res_cv["sell_recall"]

                # F1 Minority primario; desempate por suma de recalls BUY+SELL
                es_mejor = False
                if f1_min > best_score_f1 + 0.005:
                    es_mejor = True
                elif abs(f1_min - best_score_f1) <= 0.005:
                    if rec_sum > best_recall_sum:
                        es_mejor = True

                if es_mejor:
                    best_score_f1 = f1_min
                    best_recall_sum = rec_sum
                    best_config = {
                        "N": N,
                        "threshold": th,
                        "ratio": ratio,
                        "cv_results": res_cv
                    }

    if not best_config:
        return {
            "ok": False,
            "mensaje": "No se pudo encontrar ninguna configuración válida en el Grid Search.",
            "datos": {}
        }
        
    best_N = best_config["N"]
    best_th = best_config["threshold"]
    best_ratio = best_config["ratio"]
    print(f"[Training] Mejor config: N={best_N}, th={best_th}, ratio={best_ratio} "
          f"| CV F1M={round(best_score_f1*100, 2)}%")

    # ── Dataset final con la mejor configuración ───────────────────────────
    muestras_finales = generar_dataset(best_N, best_th, klines_dict_train)
    M = len(muestras_finales)

    # Validación interna temporal: últimos 20% del período de entrenamiento
    split_idx = int(M * 0.80)
    train_raw = muestras_finales[:split_idx]
    val_final = muestras_finales[split_idx:]

    # ── Entrenar modelo global y modelos por símbolo ──────────────────────
    def entrenar_y_calibrar_submodelo(train_samples: list[dict], val_samples: list[dict], ratio: float) -> dict:
        # Balanceo HOLD por undersampling
        buys = [m for m in train_samples if m["recomendacion"] == "BUY"]
        sells = [m for m in train_samples if m["recomendacion"] == "SELL"]
        holds = [m for m in train_samples if m["recomendacion"] == "HOLD"]
        
        target_holds = int(ratio * max(len(buys), len(sells)))
        random.Random(42).shuffle(holds)
        if len(holds) > target_holds:
            holds = holds[:target_holds]
        train_balanced = buys + sells + holds
        
        submodel = bayesian_model.entrenar_modelo(train_balanced)
        
        # Calibrate
        try:
            cal_tabla = bayesian_model._construir_tabla_calibracion(val_samples, submodel)
            submodel["calibracion_isotonica"] = cal_tabla
        except Exception as e:
            print(f"[Training] Error en calibración de submodelo: {e}")
            cal_tabla = None
            
        # Evaluate internally on val_samples
        eval_res = bayesian_model.evaluar_modelo(val_samples, submodel)
        
        # Calculate baseline
        val_labels = [m["recomendacion"] for m in val_samples]
        counts_val = Counter(val_labels)
        clase_may, count_may = counts_val.most_common(1)[0] if counts_val else ("HOLD", 0)
        baseline_accuracy = count_may / len(val_samples) if val_samples else 0.0
        
        submodel.update({
            "accuracy":                eval_res.get("accuracy"),
            "accuracy_pct":            eval_res.get("accuracy_pct"),
            "accuracy_validacion":     eval_res.get("accuracy"),
            "accuracy_validacion_pct": eval_res.get("accuracy_pct"),
            "balanced_accuracy":       eval_res.get("balanced_accuracy"),
            "balanced_accuracy_pct":   eval_res.get("balanced_accuracy_pct"),
            "f1_macro":                eval_res.get("f1_macro"),
            "f1_macro_pct":            round(eval_res.get("f1_macro", 0.0) * 100, 2),
            "precision_recall_f1":     eval_res.get("metrics_per_class"),
            "matriz_confusion":        eval_res.get("confusion_matrix"),
            "total_validacion":        eval_res.get("total_validacion"),
            "correctos_validacion":    eval_res.get("correctos"),
            "total_muestras":          len(train_balanced),
            "baseline_accuracy":       round(baseline_accuracy, 4),
            "baseline_accuracy_pct":   round(baseline_accuracy * 100, 2),
        })
        return submodel

    # 1. Train Global Model
    global_model = entrenar_y_calibrar_submodelo(train_raw, val_final, best_ratio)
    
    global_model["best_N"] = best_N
    global_model["best_threshold"] = best_th
    global_model["best_ratio"] = best_ratio
    global_model["pares_usados"] = list(klines_dict_train.keys())
    global_model["pares_oos"] = list(klines_dict_oos.keys())
    
    modelo_candidato = {
        "global": global_model,
        "tipo": "Red Bayesiana discreta",
        "version": datetime.now().strftime("%Y%m%d%H%M%S"),
        "fecha_entrenamiento": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "best_N": best_N,
        "best_threshold": best_th,
        "best_ratio": best_ratio,
        "pares_usados": list(klines_dict_train.keys()),
        "pares_oos": list(klines_dict_oos.keys()),
        "desplegable": False
    }

    # 2. Train Symbol-Specific Models
    for par in klines_dict_train.keys():
        train_par = [m for m in train_raw if m.get("par") == par]
        val_par = [m for m in val_final if m.get("par") == par]
        
        if len(train_par) >= 20 and len(val_par) >= 5:
            try:
                par_model = entrenar_y_calibrar_submodelo(train_par, val_par, best_ratio)
                par_model["best_N"] = best_N
                par_model["best_threshold"] = best_th
                par_model["best_ratio"] = best_ratio
                par_model["pares_usados"] = [par]
                modelo_candidato[par] = par_model
            except Exception as e:
                print(f"[Training] Error entrenando submodelo para {par}: {e}")
                
    # ── Generar y evaluar OOS real en el modelo completo (con submodelos específicos) ──
    muestras_oos = generar_dataset(best_N, best_th, klines_dict_oos)
    evaluacion_oos = None
    if muestras_oos:
        try:
            evaluacion_oos = bayesian_model.evaluar_modelo(muestras_oos, modelo_candidato)
            print(f"[Training] Evaluación OOS real del modelo completo: acc={evaluacion_oos['accuracy_pct']}% "
                  f"({evaluacion_oos['correctos']}/{evaluacion_oos['total_validacion']} muestras)")
        except Exception as e:
            print(f"[Training] Warning evaluación OOS: {e}")

    # Check deployment guards on full candidate model evaluated on OOS real
    eval_target = evaluacion_oos if evaluacion_oos else global_model
    f1_macro = eval_target["f1_macro"]
    rec_buy = eval_target["metrics_per_class"].get("BUY", {}).get("recall", 0.0)
    rec_sell = eval_target["precision_recall_f1"].get("SELL", {}).get("recall", 0.0) if "precision_recall_f1" in eval_target else eval_target["metrics_per_class"].get("SELL", {}).get("recall", 0.0)
    balanced_acc = eval_target["balanced_accuracy"]
    
    # Guards: F1 macro >= 30%, recalls >= 8% (BUY) / 15% (SELL), balanced accuracy >= 30%
    desplegable = (
        (f1_macro >= 0.30) and
        (rec_buy >= 0.08) and
        (rec_sell >= 0.15) and
        (balanced_acc >= 0.30)
    )
    
    modelo_candidato["desplegable"] = desplegable
    global_model["desplegable"] = desplegable
    for key in modelo_candidato:
        if isinstance(modelo_candidato[key], dict) and "desplegable" in modelo_candidato[key]:
            modelo_candidato[key]["desplegable"] = desplegable

    modelo_candidato["evaluacion_oos_real"] = evaluacion_oos
    global_model["evaluacion_oos_real"] = evaluacion_oos

    # Predictions distribution analysis
    predicciones_val = []
    for m in val_final:
        try:
            probs, _ = bayesian_model.inferir_probabilidades(
                bayesian_model._muestra_a_evidencia(m), m.get("par"), modelo_candidato
            )
            pred = max(probs, key=probs.get)
        except Exception:
            pred = "HOLD"
        predicciones_val.append(pred)
        
    train_dist = dict(Counter(m["recomendacion"] for m in train_raw))
    val_dist   = dict(Counter(m["recomendacion"] for m in val_final))
    pred_dist  = dict(Counter(predicciones_val))
    oos_dist   = dict(Counter(m["recomendacion"] for m in muestras_oos)) if muestras_oos else {}
    regimen_dist = dict(Counter(m.get("regimen", "lateral") for m in muestras_finales))

    modelo_candidato.update({
        "distribucion_predicciones":  pred_dist,
        "distribucion_regimenes":     regimen_dist,
        "distribucion_etiquetas": {
            "entrenamiento":            train_dist,
            "validacion":               val_dist,
            "oos_real":                 oos_dist,
        }
    })

    # ── Guardar dataset en training_data.json ─────────────────────────────
    try:
        os.makedirs(os.path.dirname(TRAINING_PATH), exist_ok=True)
        with open(TRAINING_PATH, "w", encoding="utf-8") as f:
            json.dump({
                "description": "Datos de entrenamiento (10 pares, multi-timeframe, señales sintéticas)",
                "fecha_extraccion": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "pares_usados": list(klines_dict_train.keys()),
                "samples": muestras_finales,
            }, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[Training] Warning guardando dataset: {e}")

    # ── Persistir o rechazar ──────────────────────────────────────────────
    if desplegable:
        try:
            bayesian_model.guardar_modelo(modelo_candidato)
            return {
                "ok": True,
                "mensaje": (f"Modelo optimizado (N={best_N}, th={best_th}) con submodelos segmentados "
                            f"desplegado correctamente."),
                "datos": {
                    "tipo":                     modelo_candidato.get("tipo"),
                    "version":                  modelo_candidato.get("version"),
                    "fecha_entrenamiento":       modelo_candidato.get("fecha_entrenamiento"),
                    "total_muestras":            global_model.get("total_muestras"),
                    "pares_usados":              modelo_candidato.get("pares_usados"),
                    "accuracy_validacion_pct":   global_model.get("accuracy_pct"),
                    "baseline_accuracy_pct":     global_model.get("baseline_accuracy_pct"),
                    "f1_macro_pct":              global_model.get("f1_macro_pct"),
                    "balanced_accuracy_pct":     global_model.get("balanced_accuracy_pct"),
                    "recall_buy_pct":            round(rec_buy * 100, 2),
                    "recall_sell_pct":           round(rec_sell * 100, 2),
                    "evaluacion_oos_real":        evaluacion_oos,
                    "calibracion_aplicada":      global_model.get("calibracion_isotonica") is not None,
                    "desplegable":               True,
                }
            }
        except Exception as e:
            return {"ok": False, "mensaje": f"Error persistiendo modelo: {e}", "datos": {}}
    else:
        # Guardar candidato rechazado para diagnóstico
        try:
            rej_path = os.path.join(os.path.dirname(__file__), "..",
                                    "data", "modelo_candidato_rechazado.json")
            os.makedirs(os.path.dirname(rej_path), exist_ok=True)
            with open(rej_path, "w", encoding="utf-8") as f:
                json.dump(modelo_candidato, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[Training] Warning guardando candidato rechazado: {e}")

        fallos = []
        if global_model.get("accuracy", 0) <= global_model.get("baseline_accuracy", 0) * 0.8: # relaxed accuracy constraint
            fallos.append(f"Accuracy ({global_model.get('accuracy_pct')}%) <= 80% of Baseline ({global_model.get('baseline_accuracy_pct')}%)")
        if f1_macro < 0.30:
            fallos.append(f"F1 Macro ({global_model.get('f1_macro_pct')}%) < 30.0%")
        if rec_buy < 0.08:
            fallos.append(f"Recall BUY ({round(rec_buy * 100, 2)}%) < 8.0%")
        if rec_sell < 0.15:
            fallos.append(f"Recall SELL ({round(rec_sell * 100, 2)}%) < 15.0%")

        msg = (f"Modelo rechazado. Se conserva el anterior. Detalles: "
               + ", ".join(fallos)
               + f" [Config: N={best_N}, th={best_th:.3f}]")
        return {
            "ok": False,
            "mensaje": msg,
            "datos": {
                "best_N":                  best_N,
                "best_threshold":          best_th,
                "accuracy_validacion_pct": global_model.get("accuracy_pct"),
                "baseline_accuracy_pct":   global_model.get("baseline_accuracy_pct"),
                "f1_macro_pct":            global_model.get("f1_macro_pct"),
                "recall_buy_pct":          round(rec_buy * 100, 2),
                "recall_sell_pct":         round(rec_sell * 100, 2),
                "evaluacion_oos_real":      evaluacion_oos,
                "desplegable":             False,
            }
        }


def estado_modelo():
    """Devuelve metadatos del modelo bayesiano activo."""
    modelo = bayesian_model.cargar_modelo()
    sub = modelo.get("global") or modelo
    return {
        "tipo":                    sub.get("tipo", "Red Bayesiana discreta"),
        "version":                 sub.get("version", "sin-version"),
        "fecha_entrenamiento":     sub.get("fecha_entrenamiento", "No entrenado"),
        "total_muestras":          sub.get("total_muestras", 0),
        "accuracy_validacion":     sub.get("accuracy_validacion"),
        "accuracy_validacion_pct": sub.get("accuracy_validacion_pct"),
        "baseline_accuracy":       sub.get("baseline_accuracy"),
        "baseline_accuracy_pct":   (
            sub.get("baseline_accuracy_pct")
            or round(sub.get("baseline_accuracy", 0) * 100, 2)
            if sub.get("baseline_accuracy") else None
        ),
        "f1_macro_pct":            (
            sub.get("f1_macro_pct")
            or round(sub.get("f1_macro", 0) * 100, 2)
            if sub.get("f1_macro") else None
        ),
        "f1_weighted_pct":         (
            sub.get("f1_weighted_pct")
            or round(sub.get("f1_weighted", 0) * 100, 2)
            if sub.get("f1_weighted") else None
        ),
        "balanced_accuracy_pct":   (
            sub.get("balanced_accuracy_pct")
            or round(sub.get("balanced_accuracy", 0) * 100, 2)
            if sub.get("balanced_accuracy") else None
        ),
        "metrics_clases":          sub.get("precision_recall_f1"),
        "desplegable":             sub.get("desplegable", True),
        "calibrado":               "calibracion_isotonica" in sub and bool(sub["calibracion_isotonica"]),
        "pares_usados":            modelo.get("pares_usados", PARES_PRINCIPALES),
        "pares_oos":               modelo.get("pares_oos", []),
        "best_N":                  modelo.get("best_N"),
        "best_threshold":          modelo.get("best_threshold"),
        "evaluacion_oos_real":     modelo.get("evaluacion_oos_real"),
        "distribucion_regimenes":  modelo.get("distribucion_regimenes"),
        "estado": (
            "Activo y Desplegado" if sub.get("desplegable", True)
            else "No desplegado (bajo rendimiento)"
        ),
    }


def agregar_muestra(muestra: dict) -> bool:
    """Añade una muestra real al dataset training_data.json."""
    try:
        data_json = {"description": "Datos de entrenamiento reales balanceados extraídos de Binance", "samples": []}
        if os.path.exists(TRAINING_PATH):
            try:
                with open(TRAINING_PATH, "r", encoding="utf-8") as f:
                    data_json = json.load(f)
            except Exception:
                pass
        
        if "samples" not in data_json:
            data_json["samples"] = []
            
        data_json["samples"].append(muestra)
        
        with open(TRAINING_PATH, "w", encoding="utf-8") as f:
            json.dump(data_json, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"[Training] Error al agregar muestra: {e}")
        return False


def verificar_resultados_operaciones(forzar_inmediato=False) -> dict:
    """
    Compara el precio original de las recomendaciones con el precio actual de Binance,
    determina el resultado (exitoso/fallido), actualiza la BD y añade el caso real
    como muestra de entrenamiento (feedback loop).
    """
    from database import db
    from services.market_service import obtener_precio_actual
    
    # 1. Obtener todas las recomendaciones pendientes
    ops_pendientes = db.get_operaciones_pendientes_resultado()
    
    total_procesadas = 0
    total_exitosas = 0
    total_fallidas = 0
    
    modelo = bayesian_model.cargar_modelo()
    threshold = float(modelo.get("best_threshold") or 0.015) # default 1.5%
    
    for op in ops_pendientes:
        # Check if enough time has passed (e.g. 1 hour = 3600 seconds)
        if not forzar_inmediato:
            try:
                creado_dt = datetime.strptime(op["created_at"], "%Y-%m-%d %H:%M:%S")
                ahora_utc = datetime.utcnow()
                diferencia_segundos = (ahora_utc - creado_dt).total_seconds()
                if diferencia_segundos < 3600:
                    continue  # Skip operations newer than 1 hour
            except Exception:
                pass
                
        symbol = op["cripto"]
        precio_inicial = float(op["precio_actual"] or 0)
        recomendacion = op["recomendacion"]
        
        if precio_inicial <= 0:
            continue
            
        try:
            precio_actual = obtener_precio_actual(symbol)
        except Exception as e:
            print(f"[Training] Error consultando precio actual de {symbol}: {e}")
            continue
            
        ret = (precio_actual - precio_inicial) / precio_inicial
        
        # Determinar resultado y etiqueta correcta
        resultado = "fallido"
        recomendacion_correcta = "HOLD"
        
        if recomendacion == "BUY":
            if ret >= threshold:
                resultado = "exitoso"
                recomendacion_correcta = "BUY"
            else:
                resultado = "fallido"
                recomendacion_correcta = "SELL" if ret <= -threshold else "HOLD"
                
        elif recomendacion == "SELL":
            if ret <= -threshold:
                resultado = "exitoso"
                recomendacion_correcta = "SELL"
            else:
                resultado = "fallido"
                recomendacion_correcta = "BUY" if ret >= threshold else "HOLD"
                
        elif recomendacion == "HOLD":
            if -threshold < ret < threshold:
                resultado = "exitoso"
                recomendacion_correcta = "HOLD"
            else:
                resultado = "fallido"
                recomendacion_correcta = "BUY" if ret >= threshold else "SELL"
                
        # Guardar en base de datos
        nota = f"Verificado con precio {precio_actual:.4f} (retorno: {ret*100:.2f}%, umbral: {threshold*100:.1f}%)"
        db.registrar_resultado_operacion(op["id"], resultado, estado="completada", nota=nota)
        
        # Reconstruir evidencia
        try:
            ind = json.loads(op.get("indicadores_json") or "{}")
        except Exception:
            ind = {}
            
        muestra_combinada = {
            "tendencia": op.get("tendencia"),
            "volumen": op.get("volumen"),
            "volatilidad": op.get("volatilidad"),
            "rsi_estado": ind.get("rsi_estado"),
            "macd_estado": ind.get("macd_estado"),
            "precio_vs_vwap": ind.get("precio_vs_vwap"),
            "bollinger_estado": ind.get("bollinger_estado"),
            "adx_estado": ind.get("adx_estado"),
            "pendiente_ema": ind.get("pendiente_ema"),
            "pendiente_sma": ind.get("pendiente_sma"),
            "retorno_estado": ind.get("retorno_estado"),
            "momentum_estado": ind.get("momentum_estado"),
            "recomendacion": recomendacion_correcta
        }
        
        evidencia = bayesian_model._muestra_a_evidencia(muestra_combinada)
        evidencia["recomendacion"] = recomendacion_correcta
        
        # Añadir al dataset de entrenamiento
        agregar_muestra(evidencia)
        
        total_procesadas += 1
        if resultado == "exitoso":
            total_exitosas += 1
        else:
            total_fallidas += 1
            
    return {
        "procesadas": total_procesadas,
        "exitosas": total_exitosas,
        "fallidas": total_fallidas
    }
