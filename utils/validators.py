"""
utils/validators.py
Validaciones de entrada para CryptoAdvisor.
"""

CRYPTOS_VALIDAS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "ADAUSDT", "XRPUSDT", "DOGEUSDT"]
ACCIONES_VALIDAS = ["comprar", "vender", "esperar"]


def validar_accion(accion):
    """Valida que la acción sea una de las permitidas."""
    if not accion:
        return False, "La acción es requerida."
    if accion not in ACCIONES_VALIDAS:
        return False, f"Acción inválida. Debe ser: {', '.join(ACCIONES_VALIDAS)}"
    return True, ""


def validar_cripto(symbol):
    """Valida que el símbolo de cripto sea uno de los permitidos."""
    if not symbol:
        return False, "El símbolo de la criptomoneda es requerido."
    if symbol not in CRYPTOS_VALIDAS:
        return False, f"Criptomoneda inválida. Opciones: {', '.join(CRYPTOS_VALIDAS)}"
    return True, ""


def validar_credenciales(username, password):
    """Valida que las credenciales tengan el formato mínimo."""
    if not username or not username.strip():
        return False, "El nombre de usuario es requerido."
    if not password or not password.strip():
        return False, "La contraseña es requerida."
    if len(username) < 3:
        return False, "El usuario debe tener al menos 3 caracteres."
    if len(password) < 4:
        return False, "La contraseña debe tener al menos 4 caracteres."
    return True, ""


def validar_operacion_id(operacion_id):
    """Valida que el ID de operación sea un número entero positivo."""
    try:
        oid = int(operacion_id)
        if oid <= 0:
            return False, "ID de operación inválido."
        return True, ""
    except (ValueError, TypeError):
        return False, "ID de operación debe ser un número entero."