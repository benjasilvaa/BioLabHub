from flask import Blueprint, render_template, session, redirect, url_for, flash
from db import ejecutar_select
from datetime import datetime

home_bp = Blueprint("home_bp", __name__)

@home_bp.route("/home")
def home():
    # Invitado: puede acceder a la home sin estar autenticado con usuario_id
    if "usuario_id" not in session and session.get("rol") != "invitado":
        flash("Debes iniciar sesión primero.", "error")
        return redirect(url_for("login_bp.login"))

    # Si es invitado, devolvemos dashboard vacío y stats en cero
    if session.get("rol") == "invitado":
        return render_template(
            "home/Home.html",
            experimentos=[],
            muestras=[],
            equipos=[],
            stats={
                'experimentos_activos': 0,
                'reservas_activas': 0,
                'muestras_registradas': 0,
                'reactivos_reponer': 0,
            },
        )

    usuario_id = session["usuario_id"]

    # Obtener estadísticas
    # 1. Contar experimentos activos del usuario
    experimentos_activos = ejecutar_select("""
        SELECT COUNT(*) as total 
        FROM experimentos 
        WHERE responsable_id = ? AND estado_logico = 0
    """, (usuario_id,))[0]["total"]

    # 2. Contar reservas activas del usuario
    reservas_activas = ejecutar_select("""
        SELECT COUNT(*) as total 
        FROM reservas_equipos 
        WHERE usuario_id = ? AND estado_logico = 0
        AND fecha_fin >= datetime('now')
    """, (usuario_id,))[0]["total"]

    # 3. Contar muestras del usuario
    muestras_registradas = ejecutar_select("""
        SELECT COUNT(*) as total 
        FROM muestras 
        WHERE responsable_id = ? AND estado_logico = 0
    """, (usuario_id,))[0]["total"]

    # 4. Contar reactivos con stock agotado
    reactivos_reponer = ejecutar_select("""
        SELECT COUNT(*) as total 
        FROM reactivos 
        WHERE stock <= 0 AND estado_logico = 0
    """)[0]["total"]

    # Obtener datos para las tablas
    experimentos = ejecutar_select("""
        SELECT id, titulo, descripcion, fecha_inicio, estado
        FROM experimentos
        WHERE responsable_id = ? AND estado_logico = 0
        ORDER BY fecha_inicio DESC
        LIMIT 5
    """, (usuario_id,))

    muestras = ejecutar_select("""
        SELECT id, nombre, tipo, estado, ubicacion
        FROM muestras
        WHERE responsable_id = ? AND estado_logico = 0
        ORDER BY fecha_ingreso DESC
        LIMIT 5
    """, (usuario_id,))

    equipos = ejecutar_select("""
        SELECT r.id, r.equipo, r.fecha_inicio, r.fecha_fin, r.estado
        FROM reservas_equipos r
        WHERE r.usuario_id = ? AND r.estado_logico = 0
        ORDER BY r.fecha_inicio DESC
    """, (usuario_id,))

    return render_template(
        "home/Home.html",
        experimentos=experimentos,
        muestras=muestras,
        equipos=equipos,
        stats={
            'experimentos_activos': experimentos_activos,
            'reservas_activas': reservas_activas,
            'muestras_registradas': muestras_registradas,
            'reactivos_reponer': reactivos_reponer
        }
    )