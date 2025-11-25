import sqlite3
from flask import Blueprint, render_template, session, redirect, url_for, flash, request
from db import ejecutar_select, recalcular_dvv, conectar_bd, calcular_dvh
\
admin_bp = Blueprint("admin_bp", __name__, url_prefix="/admin")
\
\
\
def require_admin():
    if "rol" not in session or session["rol"] != "admin":
        flash(" No tienes permisos para acceder a esta sección.", "error")
        return False
    return True
@admin_bp.route("/")
def admin_panel():
    if not require_admin():
        return redirect(url_for("home"))
    logs = ejecutar_select("""
        SELECT 
            a.id, a.accion, a.tabla_afectada, a.registro_id,
            a.fecha, a.ip_origen,
            u.nombre as usuario
        FROM audits_logs a
        LEFT JOIN usuarios u ON a.usuario_id = u.id
        ORDER BY a.fecha DESC
    """)
    \
\
    tablas = [\
        "usuarios", "muestras", "reactivos", "experimentos",\
        "laboratorios", "reservas_equipos", "equipos", "audits_logs"\
    ]
    \
    dv_info = []
    \
    for tabla in tablas:
        \
        try:
            if tabla in ["audits_logs"]:
                filas = ejecutar_select(f"SELECT dvh FROM {tabla}")
            else:
                filas = ejecutar_select(f"SELECT dvh FROM {tabla} WHERE estado_logico = 0")
            dvv_real = sum(f["dvh"] for f in filas if f["dvh"] is not None)
        except sqlite3.OperationalError:
            \
            dvv_real = None
        reg = ejecutar_select("SELECT dvv FROM verificaciones_verticales WHERE tabla = ?", (tabla,))
        dvv_registrado = reg[0]["dvv"] if reg else None
        \
        dv_info.append({\
            "tabla": tabla,\
            "dvv_real": dvv_real,\
            "dvv_registrado": dvv_registrado,\
            "ok": (dvv_real == dvv_registrado) if dvv_real is not None else True\
        })
    return render_template("admin/AdminPanel.html", logs=logs, dv_info=dv_info)
@admin_bp.route("/recalcular/<tabla>", methods=["POST"])
def recalcular_tabla(tabla):
    if not require_admin():
        return redirect(url_for("home"))
    conn = conectar_bd()
    cursor = conn.cursor()
    \
    try:
        filas = cursor.execute(f"SELECT * FROM {tabla}").fetchall()
        for fila in filas:
            datos = dict(fila)
            datos.pop("id", None)
            datos.pop("dvh", None)
            \
            nuevo_dvh = calcular_dvh(datos)
            cursor.execute(f"UPDATE {tabla} SET dvh = ? WHERE id = ?", (nuevo_dvh, fila["id"]))
        conn.commit()
        conn.close()
        \
\
        recalcular_dvv(tabla)
        flash(f" Integridad recalculada para la tabla {tabla}.", "success")
    except Exception as e:
        flash(f" Error recalculando {tabla}: {e}", "error")
    return redirect(url_for("admin_bp.admin_panel"))
@admin_bp.route("/recalcular_todo", methods=["POST"])
def recalcular_todo():
    if not require_admin():
        return redirect(url_for("home"))
    tablas = [\
        "usuarios", "muestras", "reactivos", "experimentos",\
        "laboratorios", "reservas_equipos", "equipos", "audits_logs"\
    ]
    \
    for tabla in tablas:
        conn = conectar_bd()
        cursor = conn.cursor()
        filas = cursor.execute(f"SELECT * FROM {tabla}").fetchall()
        \
        for fila in filas:
            datos = dict(fila)
            datos.pop("id", None)
            datos.pop("dvh", None)
            \
            nuevo_dvh = calcular_dvh(datos)
            cursor.execute(f"UPDATE {tabla} SET dvh = ? WHERE id = ?", (nuevo_dvh, fila["id"]))
        conn.commit()
        conn.close()
        \
        recalcular_dvv(tabla)
    flash(" Se recalculó la integridad de TODAS las tablas.", "success")
    return redirect(url_for("admin_bp.admin_panel"))
