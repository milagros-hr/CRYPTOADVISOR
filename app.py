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
from services import auth_service, decision_service, admin_service, training_service
from utils.validators import validar_accion, validar_cripto, validar_operacion_id
from utils.helpers import respuesta_json

app = Flask(__name__)

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config", "settings.json")
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    config = json.load(f)

app.secret_key = config["app"]["secret_key"]
db.init_db()


def login_requerido(f):
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not auth_service.esta_autenticado(session):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


def admin_requerido(f):
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not auth_service.esta_autenticado(session):
            return redirect(url_for("login"))
        if not auth_service.es_admin(session):
            return redirect(url_for("usuario_dashboard"))
        return f(*args, **kwargs)
    return wrapper


@app.route("/", methods=["GET"])
def index():
    if auth_service.esta_autenticado(session):
        if auth_service.es_admin(session):
            return redirect(url_for("admin_dashboard"))
        return redirect(url_for("usuario_dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if auth_service.esta_autenticado(session):
        return redirect(url_for("index"))

    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        usuario = auth_service.autenticar_usuario(username, password)
        if usuario:
            session["usuario_id"] = usuario["id"]
            session["username"] = usuario["username"]
            session["rol"] = usuario["rol"]

            if usuario["rol"] == "admin":
                return redirect(url_for("admin_dashboard"))
            return redirect(url_for("usuario_dashboard"))
        error = "Usuario o contraseña incorrectos."

    return render_template("login.html", error=error)


@app.route("/registro", methods=["GET", "POST"])
def registro():
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


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_requerido
def usuario_dashboard():
    criptos = config["cryptos"]
    usuario = db.get_usuario(session.get("usuario_id")) or {}
    activos_portafolio = []
    if hasattr(db, "get_portafolio_usuario"):
        activos_portafolio = db.get_portafolio_usuario(session.get("usuario_id"))
    return render_template(
        "usuario_dashboard.html",
        username=session.get("username"),
        criptos=criptos,
        cryptos=criptos,
        perfil=usuario.get("perfil_riesgo", "moderado"),
        activos_portafolio=len(activos_portafolio)
    )


@app.route("/portafolio", methods=["GET", "POST"])
@login_requerido
def portafolio():
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

    activos = db.get_portafolio_usuario(usuario_id) if hasattr(db, "get_portafolio_usuario") else []
    resumen = {"valor_invertido": 0.0, "valor_actual": 0.0, "pnl": 0.0, "pnl_pct": 0.0, "activos": 0}

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
    resumen["pnl_pct"] = (resumen["pnl"] / resumen["valor_invertido"] * 100) if resumen["valor_invertido"] > 0 else 0
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


@app.route("/api/analizar", methods=["POST"])
@login_requerido
def api_analizar():
    data = request.get_json()
    if not data:
        return jsonify(respuesta_json(False, "Datos JSON requeridos.")), 400

    symbol = data.get("symbol", "").strip().upper()
    accion = data.get("accion", "").strip().lower()
    perfil_riesgo = data.get("perfil_riesgo", "").strip().lower() or None

    ok, msg = validar_cripto(symbol)
    if not ok:
        return jsonify(respuesta_json(False, msg)), 400

    ok, msg = validar_accion(accion)
    if not ok:
        return jsonify(respuesta_json(False, msg)), 400

    try:
        resultado = decision_service.generar_analisis(
            symbol=symbol,
            accion=accion,
            usuario_id=session["usuario_id"],
            perfil_riesgo=perfil_riesgo
        )
        return jsonify(respuesta_json(True, "Análisis completado.", resultado))
    except Exception as e:
        print(f"[API] Error en /api/analizar: {e}")
        return jsonify(respuesta_json(False, f"Error interno: {str(e)}")), 500


@app.route("/api/precio/<symbol>")
@login_requerido
def api_precio(symbol):
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


@app.route("/historial")
@login_requerido
def historial():
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


@app.route("/estadisticas")
@login_requerido
def estadisticas():
    stats_base = admin_service.obtener_estadisticas() or {}
    stats = {
        **stats_base,
        "compras": stats_base.get("compras", stats_base.get("buy", 0)),
        "ventas": stats_base.get("ventas", stats_base.get("sell", 0)),
        "esperas": stats_base.get("esperas", stats_base.get("hold", 0)),
        "confianza_promedio": stats_base.get("confianza_promedio", stats_base.get("prob_promedio", 0)),
        "precision": stats_base.get("precision", 0),
    }
    operaciones = db.get_all_operaciones()

    return render_template(
        "estadisticas.html",
        stats=stats,
        estadisticas=stats,
        operaciones=operaciones,
        username=session.get("username"),
        rol=session.get("rol")
    )


@app.route("/admin")
@admin_requerido
def admin_dashboard():
    stats = admin_service.obtener_estadisticas()
    modelo = training_service.estado_modelo()
    return render_template(
        "admin_dashboard.html",
        stats=stats,
        modelo=modelo,
        username=session.get("username")
    )


@app.route("/api/admin/reentrenar", methods=["POST"])
@admin_requerido
def api_admin_reentrenar():
    resultado = training_service.reentrenar_modelo()
    status = 200 if resultado.get("ok") else 500
    return jsonify(resultado), status


@app.route("/api/admin/verificar_resultados", methods=["POST"])
@admin_requerido
def api_verificar_resultados():
    try:
        resultado = training_service.verificar_resultados_operaciones(forzar_inmediato=True)
        return jsonify(respuesta_json(True, "Resultados de recomendaciones verificados y actualizados con Binance.", resultado))
    except Exception as e:
        return jsonify(respuesta_json(False, f"Error al verificar resultados: {e}")), 500


@app.route("/api/admin/model_status")
@admin_requerido
def api_admin_model_status():
    return jsonify(respuesta_json(True, "Estado del modelo.", training_service.estado_modelo()))


@app.route("/api/admin/system_status")
@admin_requerido
def api_system_status():
    try:
        from services.market_service import estado_binance
        estado = estado_binance()
        estado.update({
            "modelo": "Red Bayesiana discreta activa",
            "base_datos": "SQLite activa",
            "nombre_sistema": "CryptoAdvisor"
        })
        return jsonify(respuesta_json(True, "Sistema operativo.", estado))
    except Exception as e:
        estado = {
            "binance": "error",
            "error": str(e),
            "modelo": "Red Bayesiana discreta activa",
            "base_datos": "SQLite activa",
            "nombre_sistema": "CryptoAdvisor"
        }
        return jsonify(respuesta_json(False, "Binance no disponible.", estado)), 503


def iniciar_feedback_job():
    import threading
    import time
    def job():
        print("[Feedback Loop] Hilo de seguimiento de recomendaciones iniciado.")
        while True:
            try:
                # Esperar 1 hora (3600 segundos)
                time.sleep(3600)
                print("[Feedback Loop] Ejecutando job periódico de seguimiento de resultados...")
                res = training_service.verificar_resultados_operaciones(forzar_inmediato=False)
                print(f"[Feedback Loop] Resultados procesados: {res}")
            except Exception as e:
                print(f"[Feedback Loop] Error en job de seguimiento: {e}")
                
    t = threading.Thread(target=job, daemon=True)
    t.start()


if __name__ == "__main__":
    print("=" * 50)
    print("  CryptoAdvisor - Sistema Inteligente de Recomendación")
    print("=" * 50)
    print(f"  URL: http://127.0.0.1:{config['app']['port']}")
    print("  Usuario: usuario / user123")
    print("  Admin:   admin   / admin123")
    print("=" * 50)
    if not config["app"]["debug"] or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        iniciar_feedback_job()
    app.run(debug=config["app"]["debug"], port=config["app"]["port"])
