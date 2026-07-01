"""
services/auth_service.py
Autenticación de usuarios para CryptoAdvisor.
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "database", "trading.db")


def autenticar_usuario(username, password):
    """
    Verifica las credenciales del usuario en la base de datos.

    Args:
        username (str): Nombre de usuario
        password (str): Contraseña en texto plano

    Returns:
        dict con datos del usuario si las credenciales son correctas, None si no.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute(
            "SELECT id, username, rol FROM usuarios WHERE username = ? AND password = ?",
            (username, password)
        )
        usuario = cursor.fetchone()
        conn.close()

        if usuario:
            return {
                "id":       usuario["id"],
                "username": usuario["username"],
                "rol":      usuario["rol"]
            }
        return None

    except Exception as e:
        print(f"[Auth] Error de autenticación: {e}")
        return None


def es_admin(session):
    """Verifica si el usuario en sesión es administrador."""
    return session.get("rol") == "admin"


def esta_autenticado(session):
    """Verifica si hay un usuario autenticado en sesión."""
    return "usuario_id" in session


def obtener_usuario_sesion(session):
    """Devuelve los datos del usuario desde la sesión."""
    return {
        "id":       session.get("usuario_id"),
        "username": session.get("username"),
        "rol":      session.get("rol")
    }

def registrar_usuario(username, email, password, perfil_riesgo="moderado"):
    """Registra usuarios nuevos desde /registro."""
    username = (username or "").strip()
    email = (email or "").strip().lower()
    password = (password or "").strip()
    perfil_riesgo = (perfil_riesgo or "moderado").strip().lower()

    if len(username) < 3:
        return False, "El usuario debe tener al menos 3 caracteres."
    if "@" not in email or "." not in email:
        return False, "Correo inválido."
    if len(password) < 4:
        return False, "La contraseña debe tener al menos 4 caracteres."
    if perfil_riesgo not in ("conservador", "moderado", "agresivo"):
        perfil_riesgo = "moderado"

    try:
        from database import db
        if db.existe_usuario(username, email):
            return False, "El usuario o correo ya existe."
        db.crear_usuario(username, email, password, perfil_riesgo)
        return True, "Usuario registrado correctamente."
    except Exception as e:
        print(f"[Auth] Error en registro: {e}")
        return False, f"No se pudo registrar: {e}"
