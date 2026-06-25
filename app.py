"""
app.py
Punto de entrada principal de CryptoAdvisor.
Servidor Flask con todas las rutas del sistema.
"""

import json
import os
from flask import (Flask, render_template, request, session,
                   redirect, url_for, jsonify)

from database import db
from services import auth_service, decision_service, admin_service
from utils.validators import validar_accion, validar_cripto, validar_operacion_id
from utils.helpers import respuesta_json

# ─────────────────────────────────────────────
# Configuración de Flask
# ─────────────────────────────────────────────
app = Flask(__name__)

# Cargar settings
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config", "settings.json")
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    config = json.load(f)

app.secret_key = config["app"]["secret_key"]

# Inicializar base de datos
db.init_db()


# ─────────────────────────────────────────────
# Helpers de autenticación
# ─────────────────────────────────────────────
def login_requerido(f):
    """Decorador: redirige al login si el usuario no está autenticado."""
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not auth_service.esta_autenticado(session):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


def admin_requerido(f):
    """Decorador: redirige si el usuario no es administrador."""
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not auth_service.esta_autenticado(session):
            return redirect(url_for("login"))
        if not auth_service.es_admin(session):
            return redirect(url_for("usuario_dashboard"))
        return f(*args, **kwargs)
    return wrapper


# ─────────────────────────────────────────────
# Rutas de Autenticación
# ─────────────────────────────────────────────
@app.route("/", methods=["GET"])
def index():
    """Redirige al dashboard correcto según el rol."""
    if auth_service.esta_autenticado(session):
        if auth_service.es_admin(session):
            return redirect(url_for("admin_dashboard"))
        return redirect(url_for("usuario_dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    """Página de inicio de sesión."""
    if auth_service.esta_autenticado(session):
        return redirect(url_for("index"))

    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        usuario = auth_service.autenticar_usuario(username, password)
        if usuario:
            session["usuario_id"] = usuario["id"]
            session["username"]   = usuario["username"]
            session["rol"]        = usuario["rol"]

            if usuario["rol"] == "admin":
                return redirect(url_for("admin_dashboard"))
            return redirect(url_for("usuario_dashboard"))
        else:
            error = "Usuario o contraseña incorrectos."

    return render_template("login.html", error=error)


<<<<<<< HEAD
@app.route("/registro", methods=["GET", "POST"])
def registro():
    """Registro de nuevos usuarios de CryptoAdvisor."""
    if auth_service.esta_autenticado(session):
        return redirect(url_for("index"))

    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()
        perfil = request.form.get("perfil_riesgo", "moderado").strip().lower()

        ok, msg = auth_service.registrar_usuario(username, email, password, perfil)
        if ok:
            return redirect(url_for("login"))
        error = msg

    return render_template("registro.html", error=error)



=======
>>>>>>> a3f45dd4a041dd5031a44a3731b083b9b7932901
@app.route("/logout")
def logout():
    """Cierra la sesión del usuario."""
    session.clear()
    return redirect(url_for("login"))


# ─────────────────────────────────────────────
# Rutas de Usuario
# ─────────────────────────────────────────────
@app.route("/dashboard")
@login_requerido
def usuario_dashboard():
    """Panel principal del usuario."""
<<<<<<< HEAD
    criptos = config["cryptos"]
    usuario = db.get_usuario(session.get("usuario_id")) or {}
    activos_portafolio = db.get_portafolio_usuario(session.get("usuario_id"))
    return render_template(
        "usuario_dashboard.html",
        username=session.get("username"),
        criptos=criptos,
        cryptos=criptos,  # compatibilidad con plantillas antiguas
        perfil=usuario.get("perfil_riesgo", "moderado"),
        activos_portafolio=len(activos_portafolio)
    )



@app.route("/portafolio", methods=["GET", "POST"])
@login_requerido
def portafolio():
    """
    Portafolio personal manual según RF-10/RF-11:
    el usuario registra activo, cantidad y precio de compra; el sistema calcula valor actual y PnL.
    """
    error = None
    mensaje = None
    usuario_id = session["usuario_id"]

    if request.method == "POST":
        try:
            cripto = request.form.get("cripto", "").strip().upper()
            cantidad = float(request.form.get("cantidad", "0") or 0)
            precio_compra = float(request.form.get("precio_compra", "0") or 0)
            notas = request.form.get("notas", "").strip()

            ok, msg = validar_cripto(cripto)
            if not ok:
                raise ValueError(msg)
            if cantidad <= 0:
                raise ValueError("La cantidad debe ser mayor a cero.")
            if precio_compra <= 0:
                raise ValueError("El precio de compra debe ser mayor a cero.")

            db.agregar_activo_portafolio(usuario_id, cripto, cantidad, precio_compra, notas)
            mensaje = "Activo agregado al portafolio correctamente."
        except Exception as e:
            error = str(e)

    activos = db.get_portafolio_usuario(usuario_id)
    resumen = {
        "valor_invertido": 0.0,
        "valor_actual": 0.0,
        "pnl": 0.0,
        "pnl_pct": 0.0,
        "activos": 0
    }

    try:
        from services.market_service import obtener_precio_actual
        for activo in activos:
            try:
                precio_actual = float(obtener_precio_actual(activo["cripto"]))
            except Exception:
                precio_actual = float(activo["precio_compra"])

            cantidad = float(activo["cantidad"])
            precio_compra = float(activo["precio_compra"])
            valor_invertido = cantidad * precio_compra
            valor_actual = cantidad * precio_actual
            pnl = valor_actual - valor_invertido
            pnl_pct = (pnl / valor_invertido * 100) if valor_invertido > 0 else 0

            activo["precio_actual"] = precio_actual
            activo["valor_invertido"] = valor_invertido
            activo["valor_actual"] = valor_actual
            activo["pnl"] = pnl
            activo["pnl_pct"] = pnl_pct

            resumen["valor_invertido"] += valor_invertido
            resumen["valor_actual"] += valor_actual
    except Exception as e:
        error = error or f"No se pudo actualizar precios del portafolio: {e}"

    resumen["pnl"] = resumen["valor_actual"] - resumen["valor_invertido"]
    resumen["pnl_pct"] = (
        resumen["pnl"] / resumen["valor_invertido"] * 100
        if resumen["valor_invertido"] > 0 else 0
    )
    resumen["activos"] = len(activos)

    return render_template(
        "portafolio.html",
        activos=activos,
        resumen=resumen,
        criptos=config["cryptos"],
        error=error,
        mensaje=mensaje,
        username=session.get("username"),
        rol=session.get("rol")
    )


@app.route("/portafolio/eliminar/<int:activo_id>", methods=["POST"])
@login_requerido
def eliminar_portafolio(activo_id):
    db.eliminar_activo_portafolio(activo_id, session["usuario_id"])
    return redirect(url_for("portafolio"))



=======
    cryptos = config["cryptos"]
    return render_template(
        "usuario_dashboard.html",
        username=session.get("username"),
        cryptos=cryptos,
        perfil=(db.get_usuario(session.get("usuario_id")) or {}).get("perfil_riesgo", "moderado")
    )


>>>>>>> a3f45dd4a041dd5031a44a3731b083b9b7932901
@app.route("/api/analizar", methods=["POST"])
@login_requerido
def api_analizar():
    """
    API: Analiza el mercado y genera una predicción bayesiana.
    Body JSON: { "symbol": "BTCUSDT", "accion": "comprar" }
    """
    data = request.get_json()
    if not data:
        return jsonify(respuesta_json(False, "Datos JSON requeridos.")), 400

    symbol = data.get("symbol", "").strip().upper()
    accion = data.get("accion", "").strip().lower()
    perfil_riesgo = data.get("perfil_riesgo", "").strip().lower() or None
<<<<<<< HEAD
=======

>>>>>>> a3f45dd4a041dd5031a44a3731b083b9b7932901
    # Validaciones
    ok, msg = validar_cripto(symbol)
    if not ok:
        return jsonify(respuesta_json(False, msg)), 400

    ok, msg = validar_accion(accion)
    if not ok:
        return jsonify(respuesta_json(False, msg)), 400

    try:
        resultado = decision_service.generar_analisis(
            symbol     = symbol,
            accion     = accion,
            usuario_id = session["usuario_id"],
            perfil_riesgo = perfil_riesgo
        )
<<<<<<< HEAD

=======
>>>>>>> a3f45dd4a041dd5031a44a3731b083b9b7932901
        return jsonify(respuesta_json(True, "Análisis completado.", resultado))
    except Exception as e:
        print(f"[API] Error en /api/analizar: {e}")
        return jsonify(respuesta_json(False, f"Error interno: {str(e)}")), 500


@app.route("/api/precio/<symbol>")
@login_requerido
def api_precio(symbol):
    """API: Devuelve el precio actual de una criptomoneda."""
    ok, msg = validar_cripto(symbol.upper())
    if not ok:
        return jsonify(respuesta_json(False, msg)), 400

    try:
        from services.market_service import obtener_precio_actual
        precio = obtener_precio_actual(symbol.upper())
        return jsonify(respuesta_json(True, "OK", {"symbol": symbol, "precio": precio}))
    except Exception as e:
        return jsonify(respuesta_json(False, f"No se pudo obtener precio: {str(e)}")), 503


@app.route("/api/perfil-riesgo", methods=["POST"])
@login_requerido
def api_perfil_riesgo():
    """API: actualiza el perfil de riesgo del usuario."""
    data = request.get_json() or {}
    perfil = data.get("perfil_riesgo", "moderado").strip().lower()
    try:
        resultado = decision_service.actualizar_perfil_riesgo(session["usuario_id"], perfil)
        return jsonify(respuesta_json(True, "Perfil de riesgo actualizado.", resultado))
    except Exception as e:
        return jsonify(respuesta_json(False, str(e))), 400


@app.route("/api/indicadores/<symbol>")
@login_requerido
def api_indicadores(symbol):
    """API: devuelve indicadores técnicos calculados en backend."""
    ok, msg = validar_cripto(symbol.upper())
    if not ok:
        return jsonify(respuesta_json(False, msg)), 400
    try:
        from services.market_service import analizar_mercado
        mercado = analizar_mercado(symbol.upper())
        return jsonify(respuesta_json(True, "Indicadores OK", {
            "symbol": symbol.upper(),
            "indicadores": mercado.get("indicadores", {}),
            "ticker_24h": mercado.get("ticker_24h", {}),
            "book": mercado.get("book", {}),
            "velas": mercado.get("velas", []),
        }))
    except Exception as e:
        return jsonify(respuesta_json(False, f"No se pudieron obtener indicadores: {str(e)}")), 503


# ─────────────────────────────────────────────
# Rutas del Historial
# ─────────────────────────────────────────────
@app.route("/historial")
@login_requerido
def historial():
    """Muestra el historial de operaciones."""
    if auth_service.es_admin(session):
        operaciones = decision_service.obtener_todo_historial()
    else:
        operaciones = decision_service.obtener_historial_usuario(session["usuario_id"])

    return render_template(
        "historial.html",
        operaciones=operaciones,
        username=session.get("username"),
        rol=session.get("rol")
    )


# ─────────────────────────────────────────────
# Rutas de Estadísticas
# ─────────────────────────────────────────────
@app.route("/estadisticas")
@login_requerido
def estadisticas():
<<<<<<< HEAD
    """Muestra estadísticas del sistema."""
    stats_base = admin_service.obtener_estadisticas() or {}
    stats = {
        **stats_base,
        "compras": stats_base.get("compras", stats_base.get("buy", 0)),
        "ventas": stats_base.get("ventas", stats_base.get("sell", 0)),
        "esperas": stats_base.get("esperas", stats_base.get("hold", 0)),
        "confianza_promedio": stats_base.get("confianza_promedio", stats_base.get("prob_promedio", 0)),
        "precision": stats_base.get("precision", 0),
    }
=======
    stats_base = admin_service.obtener_estadisticas() or {}

    stats = {
        "compras": stats_base.get("compras", 0),
        "ventas": stats_base.get("ventas", 0),
        "esperas": stats_base.get("esperas", stats_base.get("hold", 0)),
        "total": stats_base.get("total", 0),
        "precision": stats_base.get("precision", 0),
        "confianza_promedio": stats_base.get("confianza_promedio", 0)
    }

>>>>>>> a3f45dd4a041dd5031a44a3731b083b9b7932901
    operaciones = db.get_all_operaciones()

    return render_template(
        "estadisticas.html",
        stats=stats,
<<<<<<< HEAD
=======
        estadisticas=stats,
>>>>>>> a3f45dd4a041dd5031a44a3731b083b9b7932901
        operaciones=operaciones,
        username=session.get("username"),
        rol=session.get("rol")
    )

<<<<<<< HEAD

=======
>>>>>>> a3f45dd4a041dd5031a44a3731b083b9b7932901
# ─────────────────────────────────────────────
# Rutas de Administrador
# ─────────────────────────────────────────────
@app.route("/admin")
@admin_requerido
def admin_dashboard():
    """Panel principal del administrador."""
    pendientes  = admin_service.obtener_solicitudes_pendientes()
    stats       = admin_service.obtener_estadisticas()
    return render_template(
        "admin_dashboard.html",
        pendientes=pendientes,
        stats=stats,
        username=session.get("username")
    )


@app.route("/api/admin/aprobar/<int:operacion_id>", methods=["POST"])
@admin_requerido
def api_aprobar(operacion_id):
    """API: Aprueba una operación pendiente."""
    ok, msg = validar_operacion_id(operacion_id)
    if not ok:
        return jsonify(respuesta_json(False, msg)), 400

    data = request.get_json() or {}
    nota = data.get("nota", "Aprobada por el administrador.")

    resultado = admin_service.aprobar_operacion(operacion_id, nota)
    status = 200 if resultado["ok"] else 500
    return jsonify(resultado), status


@app.route("/api/admin/rechazar/<int:operacion_id>", methods=["POST"])
@admin_requerido
def api_rechazar(operacion_id):
    """API: Rechaza una operación pendiente."""
    ok, msg = validar_operacion_id(operacion_id)
    if not ok:
        return jsonify(respuesta_json(False, msg)), 400

    data = request.get_json() or {}
    nota = data.get("nota", "Rechazada por el administrador.")

    resultado = admin_service.rechazar_operacion(operacion_id, nota)
    status = 200 if resultado["ok"] else 500
    return jsonify(resultado), status


@app.route("/api/admin/pendientes")
@admin_requerido
def api_pendientes():
    """API: Devuelve las operaciones pendientes en JSON."""
    pendientes = admin_service.obtener_solicitudes_pendientes()
    return jsonify(respuesta_json(True, "OK", pendientes))


@app.route("/api/admin/system_status")
@admin_requerido
def api_system_status():
    """API: monitoreo básico del sistema, Binance, modelo y base de datos."""
    try:
        from services.market_service import estado_binance
        estado = estado_binance()
        estado.update({
            "modelo": "Naive Bayes + indicadores técnicos activo",
            "base_datos": "SQLite activa",
            "nombre_sistema": "CryptoAdvisor"
        })
        return jsonify(respuesta_json(True, "Sistema operativo.", estado))
    except Exception as e:
        estado = {
            "binance": "error",
            "error": str(e),
            "modelo": "Naive Bayes + indicadores técnicos activo",
            "base_datos": "SQLite activa",
            "nombre_sistema": "CryptoAdvisor"
        }
        return jsonify(respuesta_json(False, "Binance no disponible.", estado)), 503


# ─────────────────────────────────────────────
# Arranque
# ─────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 50)
    print("  CryptoAdvisor - Sistema Inteligente de Recomendación")
    print("=" * 50)
    print(f"  URL: http://127.0.0.1:{config['app']['port']}")
    print(f"  Usuario: usuario / user123")
    print(f"  Admin:   admin   / admin123")
    print("=" * 50)
    app.run(
        debug=config["app"]["debug"],
        port=config["app"]["port"]
    )