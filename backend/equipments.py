from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from datetime import datetime
from flask_socketio import emit
from db import (
    ejecutar_select,
    ejecutar_insert,
    ejecutar_update,
    registrar_auditoria,
    recalcular_dvv,
    calcular_dvh,
)
import base64
from cryptography.fernet import Fernet
SECRET_KEY = base64.urlsafe_b64encode(b"12345678901234567890123456789012")
fernet = Fernet(SECRET_KEY)
def encode_id(real_id: int) -> str:
    return fernet.encrypt(str(real_id).encode()).decode()
def decode_id(hashed: str) -> int:
    return int(fernet.decrypt(hashed.encode()).decode())
equipments_bp = Blueprint("equipments_bp", __name__)
@equipments_bp.route("/equipreserve")
def equipreserve():
    if "usuario_id" not in session:
        flash("Debes iniciar sesión para acceder.", "error")
        return redirect(url_for("login_bp.login"))
    equipos = ejecutar_select(
        "SELECT nombre FROM equipos WHERE estado_logico = 0 ORDER BY nombre ASC"
    )
    return render_template("equipreserve/EquipReserve.html", equipos=equipos)
@equipments_bp.route("/equipreserve/events")
def equipreserve_events():
    rol = session.get("rol")
    usuario_id = session.get("usuario_id")
    if rol == "admin":
        query = """
            SELECT r.id, r.equipo, r.fecha_inicio, r.fecha_fin, r.estado,
                   u.nombre as usuario, r.usuario_id
            FROM reservas_equipos r
            LEFT JOIN usuarios u ON r.usuario_id = u.id
            WHERE r.estado_logico = 0
        """
        eventos = ejecutar_select(query)
    else:
        query = """
            SELECT r.id, r.equipo, r.fecha_inicio, r.fecha_fin, r.estado,
                   u.nombre as usuario, r.usuario_id
            FROM reservas_equipos r
            LEFT JOIN usuarios u ON r.usuario_id = u.id
            WHERE r.estado_logico = 0 AND r.usuario_id = ?
        """
        eventos = ejecutar_select(query, (usuario_id,))
    eventos_json = []
    for e in eventos:
        color = "#1a237e" if e["usuario"] == session["nombre"] else "#90a4ae"
        eventos_json.append({
            "id": encode_id(e["id"]),
            "rid": encode_id(e["id"]),
            "title": f"{e['equipo']} ({e['usuario']})",
            "start": e["fecha_inicio"],
            "end": e["fecha_fin"],
            "color": color,
            "textColor": "#fff",
            "usuario_id": e["usuario_id"]
        })
    return jsonify(eventos_json)
@equipments_bp.route("/equipreserve", methods=["POST"])
def create_reservation():
    equipo = request.form.get("equipo")
    fecha_inicio = request.form.get("fecha_inicio")
    fecha_fin = request.form.get("fecha_fin")
    usuario_id = session.get("usuario_id")
    
    # Validar que la fecha de inicio no sea anterior a la actual
    from datetime import datetime
    try:
        fecha_inicio_dt = datetime.strptime(fecha_inicio, "%Y-%m-%dT%H:%M")
        if fecha_inicio_dt < datetime.now():
            flash("No puedes hacer reservas en fechas pasadas.", "error")
            return redirect(url_for("equipments_bp.equipreserve"))
    except ValueError:
        flash("Formato de fecha inválido.", "error")
        return redirect(url_for("equipments_bp.equipreserve"))
    if not equipo or not fecha_inicio or not fecha_fin:
        flash("Todos los campos son obligatorios.", "error")
        return redirect(url_for("equipments_bp.equipreserve"))
    conflicto = ejecutar_select("""
        SELECT * FROM reservas_equipos
        WHERE estado_logico = 0 AND equipo = ?
        AND (
            (? BETWEEN fecha_inicio AND fecha_fin) OR
            (? BETWEEN fecha_inicio AND fecha_fin)
        )
    """, (equipo, fecha_inicio, fecha_fin))
    if conflicto:
        flash(f"El equipo '{equipo}' ya está reservado en ese horario.", "error")
        return redirect(url_for("equipments_bp.equipreserve"))
    new_id = ejecutar_insert("""
        INSERT INTO reservas_equipos (equipo, fecha_inicio, fecha_fin, usuario_id, estado, dvh)
        VALUES (?, ?, ?, ?, 'Reservado', 0)
    """, (equipo, fecha_inicio, fecha_fin, usuario_id))
    datos_reserva = {
        "equipo": equipo,
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
        "usuario_id": usuario_id,
        "estado": "Reservado"
    }
    nuevo_dvh = calcular_dvh(datos_reserva)
    ejecutar_update("UPDATE reservas_equipos SET dvh=? WHERE id=?", (nuevo_dvh, new_id))
    registrar_auditoria(
        usuario_id, "CREAR RESERVA", "reservas_equipos", new_id, request.remote_addr
    )
    recalcular_dvv("reservas_equipos")
    from servidor import socketio
    socketio.emit("refresh_calendar", {})
    flash("Reserva creada correctamente.", "success")
    return redirect(url_for("equipments_bp.equipreserve"))
@equipments_bp.route("/equipreserve/get/<string:rid>")
def get_reserva(rid):
    try:
        real_id = decode_id(rid)
    except:
        return jsonify({"error": "ID no válido"}), 400
    data = ejecutar_select(
        "SELECT equipo, fecha_inicio, fecha_fin FROM reservas_equipos WHERE id=?",
        (real_id,)
    )
    if not data:
        return jsonify({"error": "Reserva no encontrada"}), 404
    return jsonify(data[0])
@equipments_bp.route("/equipreserve/edit/<string:rid>", methods=["POST"])
def edit_reserva(rid):
    try:
        real_id = decode_id(rid)
    except Exception:
        flash("ID inválido.", "error")
        return redirect(url_for("equipments_bp.equipreserve"))
    equipo = request.form.get("equipo")
    inicio = request.form.get("fecha_inicio")
    fin = request.form.get("fecha_fin")
    ejecutar_update("""
        UPDATE reservas_equipos
        SET equipo=?, fecha_inicio=?, fecha_fin=?
        WHERE id=?
    """, (equipo, inicio, fin, real_id))
    recalcular_dvv("reservas_equipos")
    from servidor import socketio
    socketio.emit("refresh_calendar", {})
    flash("Reserva editada correctamente.", "success")
    return redirect(url_for("equipments_bp.equipreserve"))
@equipments_bp.route("/equipreserve/delete/<string:rid>", methods=["POST"])
def delete_reserva(rid):
    if session.get("rol") != "admin":
        flash("Solo los administradores pueden eliminar reservas.", "error")
        return redirect(url_for("equipments_bp.equipreserve"))
    real_id = decode_id(rid)
    ejecutar_update("UPDATE reservas_equipos SET estado_logico = 1 WHERE id=?", (real_id,))
    registrar_auditoria(
        session["usuario_id"],
        "ELIMINAR RESERVA",
        "reservas_equipos",
        real_id,
        request.remote_addr
    )
    recalcular_dvv("reservas_equipos")
    from servidor import socketio
    socketio.emit("refresh_calendar", {})
    flash("Reserva eliminada correctamente.", "success")
    return redirect(url_for("equipments_bp.equipreserve"))