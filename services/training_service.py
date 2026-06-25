"""
services/training_service.py
Gestión de los datos de entrenamiento del modelo bayesiano.
Permite agregar nuevas muestras para mejorar el modelo con el tiempo.
"""

import json
import os
from datetime import datetime

TRAINING_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "training_data.json")


def cargar_datos():
    """Carga los datos de entrenamiento actuales."""
    try:
        with open(TRAINING_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[Training] Error cargando datos: {e}")
        return {"description": "", "samples": []}


def agregar_muestra(tendencia, volumen, volatilidad, accion, resultado):
    """
    Agrega una nueva muestra de entrenamiento.
    Útil para retroalimentar el modelo con el resultado real de operaciones.

    Args:
        tendencia   (str): 'alcista' | 'bajista' | 'lateral'
        volumen     (str): 'alto' | 'medio' | 'bajo'
        volatilidad (str): 'alta' | 'media' | 'baja'
        accion      (str): 'comprar' | 'vender' | 'esperar'
        resultado   (str): 'exitoso' | 'fallido'

    Returns:
        bool: True si se guardó correctamente
    """
    valores_validos = {
        "tendencia":   ["alcista", "bajista", "lateral"],
        "volumen":     ["alto", "medio", "bajo"],
        "volatilidad": ["alta", "media", "baja"],
        "accion":      ["comprar", "vender", "esperar"],
        "resultado":   ["exitoso", "fallido"]
    }

    # Validaciones
    if tendencia not in valores_validos["tendencia"]:
        return False, "Tendencia inválida"
    if volumen not in valores_validos["volumen"]:
        return False, "Volumen inválido"
    if volatilidad not in valores_validos["volatilidad"]:
        return False, "Volatilidad inválida"
    if accion not in valores_validos["accion"]:
        return False, "Acción inválida"
    if resultado not in valores_validos["resultado"]:
        return False, "Resultado inválido"

    try:
        datos = cargar_datos()
        nueva_muestra = {
            "tendencia":   tendencia,
            "volumen":     volumen,
            "volatilidad": volatilidad,
            "accion":      accion,
            "resultado":   resultado,
            "agregado":    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        datos["samples"].append(nueva_muestra)

        with open(TRAINING_PATH, "w", encoding="utf-8") as f:
            json.dump(datos, f, indent=2, ensure_ascii=False)

        return True, f"Muestra agregada. Total: {len(datos['samples'])} muestras."

    except Exception as e:
        return False, f"Error guardando muestra: {str(e)}"


def obtener_resumen():
    """Devuelve un resumen estadístico de los datos de entrenamiento."""
    datos = cargar_datos()
    muestras = datos.get("samples", [])

    if not muestras:
        return {"total": 0}

    exitosos = sum(1 for m in muestras if m["resultado"] == "exitoso")
    fallidos  = len(muestras) - exitosos

    return {
        "total":       len(muestras),
        "exitosos":    exitosos,
        "fallidos":    fallidos,
        "pct_exito":   round((exitosos / len(muestras)) * 100, 1)
    }