"""
database/db.py
Base de datos SQLite de CryptoAdvisor.
"""

import json
import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(__file__), "trading.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_column(cursor, table, column, definition):
    cursor.execute(f"PRAGMA table_info({table})")
    cols = [row[1] for row in cursor.fetchall()]
    if column not in cols:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT,
            password TEXT NOT NULL,
            rol TEXT NOT NULL DEFAULT 'usuario',
            perfil_riesgo TEXT DEFAULT 'moderado',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS operaciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            cripto TEXT NOT NULL,
            accion TEXT NOT NULL,
            recomendacion TEXT,
            precio_actual REAL,
            probabilidad REAL,
            prob_buy REAL,
            prob_sell REAL,
            prob_hold REAL,
            perfil_riesgo TEXT,
            tendencia TEXT,
            volumen TEXT,
            volatilidad TEXT,
            indicadores_json TEXT,
            parametros_json TEXT,
            advertencia TEXT,
            aviso_legal TEXT,
            estado TEXT DEFAULT 'pendiente',
            resultado TEXT,
            admin_nota TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS portafolio (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            cripto TEXT NOT NULL,
            cantidad REAL NOT NULL,
            precio_compra REAL NOT NULL,
            notas TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
        )
    """)

    for col, definition in {
        "email": "TEXT",
        "perfil_riesgo": "TEXT DEFAULT 'moderado'",
    }.items():
        _ensure_column(cursor, "usuarios", col, definition)

    for col, definition in {
        "recomendacion": "TEXT",
        "prob_buy": "REAL",
        "prob_sell": "REAL",
        "prob_hold": "REAL",
        "perfil_riesgo": "TEXT",
        "indicadores_json": "TEXT",
        "parametros_json": "TEXT",
        "advertencia": "TEXT",
        "aviso_legal": "TEXT",
    }.items():
        _ensure_column(cursor, "operaciones", col, definition)

    cursor.execute("SELECT COUNT(*) FROM usuarios WHERE username = 'admin'")
    if cursor.fetchone()[0] == 0:
        cursor.execute(
            "INSERT INTO usuarios (username, email, password, rol, perfil_riesgo) VALUES (?, ?, ?, ?, ?)",
            ("admin", "admin@cryptoadvisor.local", "admin123", "admin", "moderado")
        )

    cursor.execute("SELECT COUNT(*) FROM usuarios WHERE username = 'usuario'")
    if cursor.fetchone()[0] == 0:
        cursor.execute(
            "INSERT INTO usuarios (username, email, password, rol, perfil_riesgo) VALUES (?, ?, ?, ?, ?)",
            ("usuario", "usuario@cryptoadvisor.local", "user123", "usuario", "moderado")
        )

    conn.commit()
    conn.close()
    print("[DB] CryptoAdvisor inicializado correctamente.")


def crear_usuario(username, email, password, perfil_riesgo="moderado"):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO usuarios (username, email, password, rol, perfil_riesgo) VALUES (?, ?, ?, 'usuario', ?)",
            (username, email, password, perfil_riesgo)
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def existe_usuario(username, email=None):
    conn = get_connection()
    cursor = conn.cursor()
    if email:
        cursor.execute("SELECT id FROM usuarios WHERE username = ? OR email = ?", (username, email))
    else:
        cursor.execute("SELECT id FROM usuarios WHERE username = ?", (username,))
    row = cursor.fetchone()
    conn.close()
    return row is not None


def get_usuario(usuario_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, email, rol, perfil_riesgo FROM usuarios WHERE id = ?", (usuario_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def actualizar_perfil_riesgo(usuario_id, perfil):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE usuarios SET perfil_riesgo = ? WHERE id = ?", (perfil, usuario_id))
    conn.commit()
    conn.close()


def insertar_operacion(data):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO operaciones (
            usuario_id, cripto, accion, recomendacion, precio_actual, probabilidad,
            prob_buy, prob_sell, prob_hold, perfil_riesgo, tendencia, volumen,
            volatilidad, indicadores_json, parametros_json, advertencia, aviso_legal
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data.get("usuario_id"),
        data.get("cripto"),
        data.get("accion"),
        data.get("recomendacion"),
        data.get("precio_actual"),
        data.get("probabilidad"),
        data.get("prob_buy"),
        data.get("prob_sell"),
        data.get("prob_hold"),
        data.get("perfil_riesgo"),
        data.get("tendencia"),
        data.get("volumen"),
        data.get("volatilidad"),
        json.dumps(data.get("indicadores", {}), ensure_ascii=False),
        json.dumps(data.get("parametros", {}), ensure_ascii=False),
        data.get("advertencia"),
        data.get("aviso_legal"),
    ))
    conn.commit()
    operacion_id = cursor.lastrowid
    conn.close()
    return operacion_id


def registrar_resultado_operacion(operacion_id, resultado, estado="completada", nota=""):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE operaciones
        SET resultado = ?, estado = ?, admin_nota = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (resultado, estado, nota, operacion_id))
    conn.commit()
    rows = cursor.rowcount
    conn.close()
    return rows > 0


def get_operaciones_pendientes_resultado():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM operaciones
        WHERE resultado IS NULL OR resultado = ''
        ORDER BY created_at DESC
    """)
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_operaciones_by_usuario(usuario_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM operaciones
        WHERE usuario_id = ?
        ORDER BY created_at DESC
    """, (usuario_id,))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_all_operaciones():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT o.*, u.username
        FROM operaciones o
        LEFT JOIN usuarios u ON u.id = o.usuario_id
        ORDER BY o.created_at DESC
    """)
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows





def get_estadisticas():
    conn = get_connection()
    cursor = conn.cursor()
    stats = {}

    cursor.execute("SELECT COUNT(*) FROM operaciones")
    stats["total"] = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM operaciones WHERE estado = 'pendiente'")
    stats["pendientes"] = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM operaciones WHERE estado = 'aprobada'")
    stats["aprobadas"] = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM operaciones WHERE estado = 'rechazada'")
    stats["rechazadas"] = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM operaciones WHERE recomendacion = 'BUY'")
    stats["buy"] = stats["compras"] = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM operaciones WHERE recomendacion = 'SELL'")
    stats["sell"] = stats["ventas"] = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM operaciones WHERE recomendacion = 'HOLD'")
    stats["hold"] = stats["esperas"] = cursor.fetchone()[0]

    cursor.execute("SELECT AVG(probabilidad) FROM operaciones")
    avg = cursor.fetchone()[0]
    stats["prob_promedio"] = stats["confianza_promedio"] = round(avg * 100, 2) if avg else 0

    cursor.execute("""
        SELECT cripto, COUNT(*) as total
        FROM operaciones
        GROUP BY cripto
        ORDER BY total DESC
        LIMIT 5
    """)
    stats["top_cryptos"] = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return stats


def agregar_activo_portafolio(usuario_id, cripto, cantidad, precio_compra, notas=""):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO portafolio (usuario_id, cripto, cantidad, precio_compra, notas)
        VALUES (?, ?, ?, ?, ?)
    """, (usuario_id, cripto, float(cantidad), float(precio_compra), notas))
    conn.commit()
    activo_id = cursor.lastrowid
    conn.close()
    return activo_id


def actualizar_activo_portafolio(activo_id, usuario_id, cripto, cantidad, precio_compra, notas=""):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE portafolio
        SET cripto = ?, cantidad = ?, precio_compra = ?, notas = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ? AND usuario_id = ?
    """, (cripto, float(cantidad), float(precio_compra), notas, activo_id, usuario_id))
    conn.commit()
    filas = cursor.rowcount
    conn.close()
    return filas > 0


def eliminar_activo_portafolio(activo_id, usuario_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM portafolio WHERE id = ? AND usuario_id = ?", (activo_id, usuario_id))
    conn.commit()
    filas = cursor.rowcount
    conn.close()
    return filas > 0


def get_portafolio_usuario(usuario_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM portafolio
        WHERE usuario_id = ?
        ORDER BY created_at DESC
    """, (usuario_id,))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows
