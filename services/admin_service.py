"""
services/admin_service.py
Lógica de negocio para el administrador del sistema CryptoAdvisor.
"""

from database import db


def obtener_estadisticas():
    """Devuelve estadísticas del sistema para el dashboard del admin."""
    return db.get_estadisticas()


def obtener_todo_historial():
    """Devuelve todo el historial de operaciones."""
    return db.get_all_operaciones()