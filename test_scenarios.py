"""
test_scenarios.py
Script de diagnóstico y validación de escenarios para la Red Bayesiana en CryptoAdvisor.
Mide la respuesta ante perfiles de riesgo, diferenciación por criptomoneda,
evaluación de la acción del usuario y genera explicaciones bayesianas detalladas.
"""

import sys
import os

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
if PROJECT_DIR not in sys.path:
    sys.path.append(PROJECT_DIR)

from models import bayesian_model

def run_tests():
    print("=" * 60)
    print("      CryptoAdvisor - Escenarios Diagnósticos de Red Bayesiana")
    print("=" * 60)
    
    # 1. Cargar modelo
    modelo = bayesian_model.cargar_modelo()
    print("Modelo cargado correctamente.")
    print(f"Versión del modelo global: {modelo.get('global', {}).get('version', 'N/A')}")
    print(f"Criptomonedas segmentadas: {list(k for k in modelo.keys() if k not in ('tipo', 'version', 'fecha_entrenamiento', 'best_N', 'best_threshold', 'best_ratio', 'pares_usados', 'pares_oos', 'desplegable', 'evaluacion_oos_real'))}")
    print("-" * 60)
    
    # 2. Definir una evidencia alcista extrema
    ind_alcista = {
        "rsi14": 15.0, # sobreventa extrema -> BUY
        "macd_histogram": 0.05,
        "precio_actual": 105.0,
        "vwap": 100.0,
        "bollinger_lower": 95.0,
        "bollinger_mid": 100.0,
        "bollinger_upper": 105.0,
        "adx14": 35.0,
        "momentum_val": 0.05,
        "rvol": 2.5,
        "volatilidad_sd": 0.012
    }
    
    # Definir evidencia bajista extrema
    ind_bajista = {
        "rsi14": 85.0, # sobrecompra extrema -> SELL
        "macd_histogram": -0.05,
        "precio_actual": 95.0,
        "vwap": 100.0,
        "bollinger_lower": 95.0,
        "bollinger_mid": 100.0,
        "bollinger_upper": 105.0,
        "adx14": 35.0,
        "momentum_val": -0.05,
        "rvol": 2.5,
        "volatilidad_sd": 0.012
    }

    # 3. Test de perfiles de riesgo y diferenciación por criptomoneda
    print("TEST 1: Diferenciación de predicciones por criptomoneda para evidencia alcista")
    for symbol in ["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT"]:
        pred = bayesian_model.predecir(
            tendencia="alcista",
            volumen="extremo",
            volatilidad="media",
            accion="comprar",
            indicadores=ind_alcista,
            perfil_riesgo="moderado",
            symbol=symbol
        )
        print(f"Símbolo: {symbol:<9} | Rec: {pred['recomendacion']:<4} | Prob: {pred['probabilidad_pct']:.2f}% | Confianza: {pred['confianza']}")
        print(f"  Detalle Probabilidades: {pred['probabilidades']}")
        print(f"  Mensaje Acción Evaluada ({pred['evaluacion_accion']['accion_consultada']}): {pred['evaluacion_accion']['mensaje']}")
    
    print("-" * 60)
    print("TEST 2: Influencia del perfil de riesgo (Conservador vs Moderado vs Agresivo) en BTCUSDT")
    for perfil in ["conservador", "moderado", "agresivo"]:
        pred = bayesian_model.predecir(
            tendencia="alcista",
            volumen="extremo",
            volatilidad="media",
            accion="comprar",
            indicadores=ind_alcista,
            perfil_riesgo=perfil,
            symbol="BTCUSDT"
        )
        print(f"Perfil: {perfil:<12} | Rec: {pred['recomendacion']:<4} | Umbral: {pred['umbral_perfil']:.2f} | Prob: {pred['probabilidad_pct']:.2f}%")
        
    print("-" * 60)
    print("TEST 3: Respuesta a la acción consultada por el usuario (BUY vs SELL vs HOLD) en ETHUSDT")
    for accion in ["comprar", "vender", "esperar"]:
        pred = bayesian_model.predecir(
            tendencia="bajista",
            volumen="bajo",
            volatilidad="baja",
            accion=accion,
            indicadores=ind_bajista,
            perfil_riesgo="moderado",
            symbol="ETHUSDT"
        )
        eval_act = pred["evaluacion_accion"]
        print(f"Acción consultada: {accion:<8} -> Mapeado: {eval_act['accion_consultada']:<4}")
        print(f"  Mensaje de Inferencia: {eval_act['mensaje']}")
        print(f"  Detalles: Éxito={round(eval_act['probabilidad_exito']*100,2)}%, Pérdida={round(eval_act['riesgo_perdida']*100,2)}%")

    print("-" * 60)
    print("TEST 4: Explicación Bayesiana Detallada (Evidencia) en BTCUSDT")
    pred = bayesian_model.predecir(
        tendencia="alcista",
        volumen="extremo",
        volatilidad="media",
        accion="comprar",
        indicadores=ind_alcista,
        perfil_riesgo="moderado",
        symbol="BTCUSDT"
    )
    expl = pred["explicacion_bayeseana"]
    print(f"Recomendación final: {pred['recomendacion']}")
    print(f"Razón principal: {expl['razon_principal']}")
    print(f"Evidencias a favor de BUY: {expl['evidencias_favor_buy']}")
    print(f"Evidencias a favor de SELL: {expl['evidencias_favor_sell']}")
    print("=" * 60)

if __name__ == "__main__":
    run_tests()
