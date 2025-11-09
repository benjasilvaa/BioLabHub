from flask import Blueprint, render_template, request, redirect, url_for, session, flash, Response, jsonify
from datetime import datetime
import json
import time

from db import (
    ejecutar_select,
    ejecutar_insert,
    ejecutar_update,
)

equipments_bp = Blueprint("equipments_bp", __name__)

# --- Página principal ---
@equipments_bp.route("/equipreserve")
def equipreserve():
    if "nombre" not in session:
        flash("⚠️ Debes iniciar sesión para acceder.", "error")
        return redirect(url_for("login_bp.login"))

    equipos = ejecutar_select("SELECT nombre FROM equipos WHERE estado_logico = 0 ORDER BY nombre ASC")
    return render_template("equipreserve/EquipReserve.html", equipos=equipos)


# --- API de eventos para FullCalendar ---
@equipments_bp.route("/equipreserve/events")
def equipreserve_events():
    rol = session.get("rol")
    usuario_id = session.get("usuario_id")

    if rol == "admin":
        query = """
            SELECT r.id, r.equipo, r.fecha_inicio, r.fecha_fin, r.estado, u.nombre as usuario
            FROM reservas_equipos r
            LEFT JOIN usuarios u ON r.usuario_id = u.id
            WHERE r.estado_logico = 0
        """
        eventos = ejecutar_select(query)
    else:
        query = """
            SELECT r.id, r.equipo, r.fecha_inicio, r.fecha_fin, r.estado, u.nombre as usuario
            FROM reservas_equipos r
            LEFT JOIN usuarios u ON r.usuario_id = u.id
            WHERE r.estado_logico = 0 AND r.usuario_id = ?
        """
        eventos = ejecutar_select(query, (usuario_id,))

    eventos_json = []
    for e in eventos:
        color = "#1a237e" if e["usuario"] == session["nombre"] else "#90a4ae"
        eventos_json.append({
            "id": e["id"],
            "title": f"{e['equipo']} ({e['usuario']})",
            "start": e["fecha_inicio"],
            "end": e["fecha_fin"],
            "color": color,
            "textColor": "#fff"
        })

    return jsonify(eventos_json)


# --- Crear nueva reserva ---
@equipments_bp.route("/equipreserve/add", methods=["POST"])
def add_reserva():
    equipo = request.form.get("equipo")
    fecha_inicio = request.form.get("fecha_inicio")
    fecha_fin = request.form.get("fecha_fin")
    usuario_id = session.get("usuario_id")

    # Validación simple
    if not equipo or not fecha_inicio or not fecha_fin:
        flash("❌ Todos los campos son obligatorios.", "error")
        return redirect(url_for("equipments_bp.equipreserve"))

    # Verificar conflicto de horario
    conflicto = ejecutar_select("""
        SELECT * FROM reservas_equipos
        WHERE estado_logico = 0 AND equipo = ? 
        AND (
            (? BETWEEN fecha_inicio AND fecha_fin) OR
            (? BETWEEN fecha_inicio AND fecha_fin)
        )
    """, (equipo, fecha_inicio, fecha_fin))

    if conflicto:
        flash(f"⚠️ El equipo '{equipo}' ya está reservado en ese rango de fechas.", "error")
        return redirect(url_for("equipments_bp.equipreserve"))

    ejecutar_insert("""
        INSERT INTO reservas_equipos (equipo, fecha_inicio, fecha_fin, usuario_id, estado)
        VALUES (?, ?, ?, ?, 'Reservado')
    """, (equipo, fecha_inicio, fecha_fin, usuario_id))

    flash(f"✅ Reserva creada correctamente para {equipo}.", "success")
    return redirect(url_for("equipments_bp.equipreserve"))


# --- Eliminar reserva (solo admin) ---
@equipments_bp.route("/equipreserve/delete/<int:id>")
def delete_reserva(id):
    if session.get("rol") != "admin":
        flash("❌ Solo los administradores pueden eliminar reservas.", "error")
        return redirect(url_for("equipments_bp.equipreserve"))

    ejecutar_update("UPDATE reservas_equipos SET estado_logico = 1 WHERE id = ?", (id,))
    flash("🗑️ Reserva eliminada correctamente.", "success")
    return redirect(url_for("equipments_bp.equipreserve"))


# --- Stream de eventos en tiempo real ---
@equipments_bp.route("/equipreserve/stream")
def equipreserve_stream():
    def event_stream():
        while True:
            time.sleep(5)
            yield f"data: Actualización de reservas a las {datetime.now().strftime('%H:%M:%S')}\n\n"

    return Response(event_stream(), mimetype="text/event-stream")
