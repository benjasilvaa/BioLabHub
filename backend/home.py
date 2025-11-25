from flask import Blueprint, render_template, session, redirect, url_for, flash
from db import ejecutar_select
\
home_bp = Blueprint("home_bp", __name__)
\
@home_bp.route("/home")
def home():
    \
    if "usuario_id" not in session:
        flash("Debes iniciar sesión primero.", "error")
        return redirect(url_for("login_bp.login"))
    usuario_id = session["usuario_id"]
    \
\
    experimentos = ejecutar_select("""
        SELECT id, titulo, descripcion, fecha_inicio, estado
        FROM experimentos
        WHERE responsable_id = ?
          AND estado_logico = 0
        ORDER BY fecha_inicio DESC
        LIMIT 5
    """, (usuario_id,))
    \
\
    muestras = ejecutar_select("""
        SELECT id, nombre, tipo, estado, ubicacion
        FROM muestras
        WHERE responsable_id = ?
          AND estado_logico = 0
        ORDER BY fecha_ingreso DESC
        LIMIT 5
    """, (usuario_id,))
    \
\
    equipos = ejecutar_select("""
        SELECT r.id, r.equipo, r.fecha_inicio, r.fecha_fin, r.estado
        FROM reservas_equipos r
        WHERE r.usuario_id = ?
          AND r.estado_logico = 0
        ORDER BY r.fecha_inicio DESC
    """, (usuario_id,))
    \
    return render_template(\
        "home/Home.html",\
        experimentos=experimentos,\
        muestras=muestras,\
        equipos=equipos\
    )
