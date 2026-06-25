"""
utils/helpers.py
Funciones auxiliares reutilizables para CryptoAdvisor.
"""

from datetime import datetime


def formatear_precio(precio, decimales=4):
    """Formatea un precio numérico como string legible."""
    try:
        return f"${float(precio):,.{decimales}f}"
    except (ValueError, TypeError):
        return "$0.0000"


def formatear_porcentaje(valor, decimales=2):
    """Convierte un decimal a porcentaje formateado."""
    try:
        return f"{float(valor) * 100:.{decimales}f}%"
    except (ValueError, TypeError):
        return "0.00%"


def formatear_fecha(fecha_str):
    """Formatea una fecha ISO a formato legible."""
    try:
        if isinstance(fecha_str, str):
            dt = datetime.strptime(fecha_str[:19], "%Y-%m-%d %H:%M:%S")
        else:
            dt = fecha_str
        return dt.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return str(fecha_str)


def estado_badge(estado):
    """Devuelve la clase CSS Bootstrap para cada estado."""
    badges = {
        "pendiente":  "warning",
        "aprobada":   "success",
        "rechazada":  "danger"
    }
    return badges.get(estado, "secondary")


def accion_icon(accion):
    """Devuelve un emoji/icono para cada tipo de acción."""
    icons = {
        "comprar": "📈",
        "vender":  "📉",
        "esperar": "⏳"
    }
    return icons.get(accion, "❓")


def tendencia_icon(tendencia):
    """Devuelve un icono para cada tipo de tendencia."""
    icons = {
        "alcista": "🟢 ↑",
        "bajista": "🔴 ↓",
        "lateral": "🟡 →"
    }
    return icons.get(tendencia, "❓")


def cripto_nombre(symbol):
    """Devuelve el nombre completo de una criptomoneda."""
    nombres = {
        "BTCUSDT": "Bitcoin",
        "ETHUSDT": "Ethereum",
        "BNBUSDT": "BNB",
        "SOLUSDT": "Solana",
        "ADAUSDT": "Cardano"
    }
    return nombres.get(symbol, symbol)


def respuesta_json(ok, mensaje, datos=None):
    """Estructura estándar para respuestas JSON de la API."""
    resp = {"ok": ok, "mensaje": mensaje}
    if datos is not None:
        resp["datos"] = datos
    return resp