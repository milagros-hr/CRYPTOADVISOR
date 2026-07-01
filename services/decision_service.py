"""
services/decision_service.py
Servicio principal de recomendación de CryptoAdvisor.

Flujo según informe:
Usuario selecciona par -> Backend consulta Binance -> calcula indicadores ->
evalúa liquidez/volatilidad -> ejecuta inferencia bayesiana ->
guarda trazabilidad -> retorna BUY/SELL/HOLD.
"""

from __future__ import annotations

from database import db
from models import bayesian_model
from services import market_service

AVISO_LEGAL = "Este sistema no ofrece asesoramiento financiero. Invierta con responsabilidad."
AVISO_RECALIBRACION = "modelo en recalibración"


def generar_analisis(symbol: str, accion: str, usuario_id: int, perfil_riesgo: str | None = None) -> dict:
    usuario = db.get_usuario(usuario_id) or {}
    perfil = (perfil_riesgo or usuario.get("perfil_riesgo") or "moderado").lower()

    mercado = market_service.analizar_mercado(symbol)

    if not mercado["liquidez_suficiente"]:
        prediccion = {
            "recomendacion": "HOLD",
            "probabilidades": {"BUY": 0.0, "SELL": 0.0, "HOLD": 1.0},
            "probabilidad": 0.0,
            "probabilidad_pct": 0.0,
            "confianza": "No calculada",
            "color": "danger",
            "umbral_perfil": bayesian_model.PERFILES.get(perfil, 0.70),
            "perfil_riesgo": perfil,
            "variables": {},
            "mensaje": mercado["mensaje_liquidez"],
        }
    else:
        # ── GATE DE SEGURIDAD: bloquear BUY/SELL si el modelo no está listo ──
        modelo_activo = bayesian_model.cargar_modelo()
        submodelo, _ = bayesian_model.obtener_submodelo(modelo_activo, symbol)
        if submodelo.get("desplegable") is False:
            prediccion = {
                "recomendacion": "HOLD",
                "probabilidades": {"BUY": 0.0, "SELL": 0.0, "HOLD": 1.0},
                "probabilidades_calibradas": {"BUY": 0.0, "SELL": 0.0, "HOLD": 1.0},
                "probabilidad": 0.0,
                "probabilidad_pct": 0.0,
                "confianza": "No calculada",
                "color": "secondary",
                "umbral_perfil": bayesian_model.PERFILES.get(perfil, 0.70),
                "perfil_riesgo": perfil,
                "variables": {},
                "mensaje": AVISO_RECALIBRACION,
                "modelo_en_recalibracion": True,
            }
        else:
            prediccion = bayesian_model.predecir(
                mercado["tendencia"],
                mercado["volumen"],
                mercado["volatilidad"],
                accion,
                indicadores=mercado.get("indicadores", {}),
                perfil_riesgo=perfil,
                symbol=symbol,
            )

    advertencia = mercado.get("aviso_volatilidad", "")
    parametros = {
        "symbol": symbol,
        "accion_solicitada": accion,
        "perfil_riesgo": perfil,
        "umbral_perfil": prediccion.get("umbral_perfil"),
        "liquidez_suficiente": mercado.get("liquidez_suficiente"),
    }

    probs = prediccion.get("probabilidades_calibradas", {}) or prediccion.get("probabilidades", {})
    operacion_id = db.insertar_operacion({
        "usuario_id": usuario_id,
        "cripto": symbol,
        "accion": accion,
        "recomendacion": prediccion.get("recomendacion", "HOLD"),
        "precio_actual": mercado["precio_actual"],
        "probabilidad": prediccion["probabilidad"],
        "prob_buy": probs.get("BUY", 0),
        "prob_sell": probs.get("SELL", 0),
        "prob_hold": probs.get("HOLD", 0),
        "perfil_riesgo": perfil,
        "tendencia": mercado["tendencia"],
        "volumen": mercado["volumen"],
        "volatilidad": mercado["volatilidad"],
        "indicadores": mercado.get("indicadores", {}),
        "parametros": parametros,
        "advertencia": advertencia,
        "aviso_legal": AVISO_LEGAL,
    })

    return {
        "operacion_id": operacion_id,
        "mercado": mercado,
        "prediccion": prediccion,
        "aviso_legal": AVISO_LEGAL,
        "advertencia": advertencia,
    }


def obtener_historial_usuario(usuario_id: int):
    return db.get_operaciones_by_usuario(usuario_id)


def obtener_todo_historial():
    return db.get_all_operaciones()


def actualizar_perfil_riesgo(usuario_id: int, perfil: str):
    perfil = (perfil or "moderado").lower()
    if perfil not in ("conservador", "moderado", "agresivo"):
        raise ValueError("Perfil inválido. Use conservador, moderado o agresivo.")
    db.actualizar_perfil_riesgo(usuario_id, perfil)
    return {"perfil_riesgo": perfil}
