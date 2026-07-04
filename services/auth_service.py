"""
services/auth_service.py
Autenticación de usuarios para CryptoAdvisor.
"""

import sqlite3
import os
from werkzeug.security import generate_password_hash, check_password_hash

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "database", "trading.db")


def autenticar_usuario(username, password):
    """
    Verifica las credenciales del usuario en la base de datos.
    Soporta contraseñas hasheadas y migración automática de texto plano.

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

        # Obtenemos la contraseña almacenada (hash o texto plano) buscando solo por username.
        # Nunca se deben almacenar contraseñas en texto plano. Si la base de datos es comprometida,
        # las credenciales de todos los usuarios quedarían expuestas inmediatamente, permitiendo
        # accesos no autorizados no solo a este sistema, sino también a otros servicios externos
        # donde el usuario pudiera estar reutilizando la misma contraseña.
        cursor.execute(
            "SELECT id, username, rol, password FROM usuarios WHERE username = ?",
            (username,)
        )
        usuario = cursor.fetchone()

        if usuario:
            stored_password = usuario["password"]
            is_valid = False
            needs_migration = False

            # Intentar validar como hash de Werkzeug
            try:
                if check_password_hash(stored_password, password):
                    is_valid = True
            except (ValueError, TypeError):
                # Si lanza error de formato, la contraseña almacenada está en texto plano
                pass

            # Si no es un hash válido o no coincidió, comparar como texto plano para migración
            if not is_valid:
                if stored_password == password:
                    is_valid = True
                    needs_migration = True

            if is_valid:
                # Si era texto plano, realizar la migración al instante a un hash seguro
                if needs_migration:
                    hashed_password = generate_password_hash(password)
                    cursor.execute(
                        "UPDATE usuarios SET password = ? WHERE id = ?",
                        (hashed_password, usuario["id"])
                    )
                    conn.commit()

                conn.close()
                return {
                    "id":       usuario["id"],
                    "username": usuario["username"],
                    "rol":      usuario["rol"]
                }

        conn.close()
        return None

    except Exception as e:
        # Registramos solo el mensaje del error genérico, nunca la contraseña ingresada
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

def registrar_usuario(username, email, password, conoce_cripto="si", perfil_riesgo="moderado"):
    """Registra usuarios nuevos desde /registro."""
    username = (username or "").strip()
    email = (email or "").strip().lower()
    password = (password or "").strip()
    conoce_cripto = (conoce_cripto or "si").strip().lower()
    perfil_riesgo = (perfil_riesgo or "moderado").strip().lower()

    if len(username) < 3:
        return False, "El usuario debe tener al menos 3 caracteres."
    if "@" not in email or "." not in email:
        return False, "Correo inválido."
    if len(password) < 4:
        return False, "La contraseña debe tener al menos 4 caracteres."
    if conoce_cripto not in ("si", "no"):
        conoce_cripto = "si"
    if perfil_riesgo not in ("conservador", "moderado", "agresivo"):
        perfil_riesgo = "moderado"

    try:
        from database import db
        if db.existe_usuario(username, email):
            return False, "El usuario o correo ya existe."
        db.crear_usuario(username, email, password, conoce_cripto, perfil_riesgo)
        return True, "Usuario registrado correctamente."
    except Exception as e:
        print(f"[Auth] Error en registro: {e}")
        return False, f"No se pudo registrar: {e}"
