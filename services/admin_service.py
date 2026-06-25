"""
services/admin_service.py
Lógica de negocio para el administrador del sistema CryptoAdvisor.
"""

from database import db


def obtener_solicitudes_pendientes():
    """Devuelve todas las operaciones con estado pendiente."""
    return db.get_operaciones_pendientes()


def aprobar_operacion(operacion_id, nota="Operación aprobada por el administrador."):
    """
    Aprueba una operación pendiente.
    
    Args:
        operacion_id (int): ID de la operación
        nota         (str): Comentario del administrador

    Returns:
        dict con resultado de la operación
    """
    try:
        db.actualizar_estado_operacion(operacion_id, "aprobada", nota)
        return {
            "ok": True,
            "mensaje": f"Operación #{operacion_id} aprobada correctamente.",
            "estado": "aprobada"
        }
    except Exception as e:
        return {
            "ok": False,
            "mensaje": f"Error al aprobar la operación: {str(e)}",
            "estado": "error"
        }


def rechazar_operacion(operacion_id, nota="Operación rechazada por el administrador."):
    """
    Rechaza una operación pendiente.

    Args:
        operacion_id (int): ID de la operación
        nota         (str): Motivo del rechazo

    Returns:
        dict con resultado de la operación
    """
    try:
        db.actualizar_estado_operacion(operacion_id, "rechazada", nota)
        return {
            "ok": True,
            "mensaje": f"Operación #{operacion_id} rechazada correctamente.",
            "estado": "rechazada"
        }
    except Exception as e:
        return {
            "ok": False,
            "mensaje": f"Error al rechazar la operación: {str(e)}",
            "estado": "error"
        }


def obtener_estadisticas():
    """Devuelve estadísticas del sistema para el dashboard del admin."""
    return db.get_estadisticas()


def obtener_todo_historial():
    """Devuelve todo el historial de operaciones."""
    return db.get_all_operaciones()