from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from datetime import datetime
from flask_socketio import emit

# Import base DB ops
from db import (
    ejecutar_select,
    ejecutar_insert,
    ejecutar_update,
    registrar_auditoria,
    recalcular_dvv,
    calcular_dvh
)

equipments_bp = Blueprint("equipments_bp", __name__)


# -----------------------------
# 🧪 Página principal
# -----------------------------
@equipments_bp.route("/equipreserve")
def equipreserve():
    if "usuario_id" not in session:
        flash("⚠️ Debes iniciar sesión para acceder.", "error")
        return redirect(url_for("login_bp.login"))

    equipos = ejecutar_select(
        "SELECT nombre FROM equipos WHERE estado_logico = 0 ORDER BY nombre ASC"
    )

    return render_template("equipreserve/EquipReserve.html", equipos=equipos)


# -----------------------------
# 📅 Eventos para FullCalendar
# -----------------------------
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


# -----------------------------
# ➕ Crear una reserva
# -----------------------------
@equipments_bp.route("/equipreserve/add", methods=["POST"])
def add_reserva():
    equipo = request.form.get("equipo")
    fecha_inicio = request.form.get("fecha_inicio")
    fecha_fin = request.form.get("fecha_fin")
    usuario_id = session.get("usuario_id")

    if not equipo or not fecha_inicio or not fecha_fin:
        flash("❌ Todos los campos son obligatorios.", "error")
        return redirect(url_for("equipments_bp.equipreserve"))

    # Verificar conflicto de reservas
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

    # 1️⃣ Insertar con DVH temporal = 0
    new_id = ejecutar_insert("""
        INSERT INTO reservas_equipos (equipo, fecha_inicio, fecha_fin, usuario_id, estado, dvh)
        VALUES (?, ?, ?, ?, 'Reservado', 0)
    """, (equipo, fecha_inicio, fecha_fin, usuario_id))

    # 2️⃣ Calcular DVH real
    datos_reserva = {
        "equipo": equipo,
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
        "usuario_id": usuario_id,
        "estado": "Reservado"
    }

    nuevo_dvh = calcular_dvh(datos_reserva)

    # 3️⃣ Guardar DVH real
    ejecutar_update(
        "UPDATE reservas_equipos SET dvh=? WHERE id=?",
        (nuevo_dvh, new_id)
    )

    # 4️⃣ Registrar auditoría
    registrar_auditoria(
        usuario_id,
        "CREAR RESERVA",
        "reservas_equipos",
        new_id,
        request.remote_addr
    )

    # 5️⃣ Recalcular DVV
    recalcular_dvv("reservas_equipos")

    # 🔥 Notificar via WebSocket
    from servidor import socketio
    socketio.emit("refresh_calendar", {"msg": f"Nueva reserva para {equipo}"})

    flash(f"✅ Reserva creada correctamente para {equipo}.", "success")
    return redirect(url_for("equipments_bp.equipreserve"))


# -----------------------------
# 🗑️ Eliminar reserva (solo admin)
# -----------------------------
@equipments_bp.route("/equipreserve/delete/<int:id>")
def delete_reserva(id):
    if session.get("rol") != "admin":
        flash("❌ Solo los administradores pueden eliminar reservas.", "error")
        return redirect(url_for("equipments_bp.equipreserve"))

    # Soft delete
    ejecutar_update("UPDATE reservas_equipos SET estado_logico = 1 WHERE id=?", (id,))

    # Auditoría
    registrar_auditoria(
        session["usuario_id"],
        "ELIMINAR RESERVA",
        "reservas_equipos",
        id,
        request.remote_addr
    )

    recalcular_dvv("reservas_equipos")

    # WebSocket
    from servidor import socketio
    socketio.emit("refresh_calendar", {"msg": "Reserva eliminada"})

    flash("🗑️ Reserva eliminada correctamente.", "success")
    return redirect(url_for("equipments_bp.equipreserve"))
