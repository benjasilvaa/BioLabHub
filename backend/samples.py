import os
import json
import time
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, Response
from db import ejecutar_select, ejecutar_insert, ejecutar_update, registrar_auditoria, recalcular_dvv
from datetime import datetime

# 📁 Configuración de rutas
template_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend", "pages", "samples")
samples_bp = Blueprint("samples_bp", __name__, template_folder=template_dir, static_folder=template_dir)

# Variable global para eventos SSE
SAMPLE_EVENTS = []

# ===============================
# 📋 LISTAR MUESTRAS
# ===============================
@samples_bp.route("/samples")
def samples():
    if "usuario_id" not in session:
        flash("Debes iniciar sesión primero.", "error")
        return redirect(url_for("login_bp.login"))

    query_muestras = """
        SELECT m.id, m.nombre, m.tipo, m.estado, m.ubicacion, u.nombre AS responsable
        FROM muestras m
        LEFT JOIN usuarios u ON m.responsable_id = u.id
        WHERE m.estado_logico = 0
        ORDER BY m.fecha_ingreso DESC
    """
    muestras = ejecutar_select(query_muestras)

    # 🔹 Laboratorios desde la base de datos
    laboratorios = ejecutar_select("SELECT nombre FROM laboratorios WHERE estado_logico = 0 ORDER BY nombre ASC")

    return render_template("samples/samples.html", muestras=muestras, laboratorios=laboratorios)


# ===============================
# ➕ CREAR NUEVA MUESTRA
# ===============================
@samples_bp.route("/samples/add", methods=["POST"])
def add_sample():
    if "usuario_id" not in session:
        flash("Debes iniciar sesión primero.", "error")
        return redirect(url_for("login_bp.login"))

    nombre = request.form.get("nombre")
    tipo = request.form.get("tipo")
    estado = request.form.get("estado", "En almacenamiento")
    ubicacion = request.form.get("ubicacion")
    responsable_id = session["usuario_id"]

    if not nombre or not ubicacion:
        flash("Por favor, completá todos los campos obligatorios.", "error")
        return redirect(url_for("samples_bp.samples"))

    query = """
        INSERT INTO muestras (nombre, tipo, estado, responsable_id, ubicacion, estado_logico)
        VALUES (?, ?, ?, ?, ?, 0)
    """
    new_id = ejecutar_insert(query, (nombre, tipo, estado, responsable_id, ubicacion))

    registrar_auditoria(responsable_id, "CREAR MUESTRA", "muestras", new_id, request.remote_addr)
    recalcular_dvv("muestras")

    SAMPLE_EVENTS.append(f"Nueva muestra agregada: {nombre}")
    flash("✅ Muestra creada correctamente.", "success")
    return redirect(url_for("samples_bp.samples"))


# ===============================
# ✏️ ACTUALIZAR MUESTRA
# ===============================
@samples_bp.route("/samples/update/<int:id>", methods=["POST"])
def update_sample(id):
    nombre = request.form.get("nombre")
    tipo = request.form.get("tipo")
    estado = request.form.get("estado")
    ubicacion = request.form.get("ubicacion")

    query = """UPDATE muestras SET nombre=?, tipo=?, estado=?, ubicacion=? WHERE id=?"""
    ejecutar_update(query, (nombre, tipo, estado, ubicacion, id))

    registrar_auditoria(session["usuario_id"], "ACTUALIZAR MUESTRA", "muestras", id, request.remote_addr)
    recalcular_dvv("muestras")

    SAMPLE_EVENTS.append(f"Muestra '{nombre}' actualizada → Estado: {estado}")
    flash("✏️ Muestra actualizada correctamente.", "success")
    return redirect(url_for("samples_bp.samples"))


# ===============================
# 🗑️ ELIMINAR MUESTRA
# ===============================
@samples_bp.route("/samples/delete/<int:id>")
def delete_sample(id):
    ejecutar_update("UPDATE muestras SET estado_logico=1 WHERE id=?", (id,))
    registrar_auditoria(session["usuario_id"], "ELIMINAR MUESTRA", "muestras", id, request.remote_addr)
    recalcular_dvv("muestras")

    SAMPLE_EVENTS.append(f"Muestra ID {id} eliminada.")
    flash("🗑️ Muestra eliminada correctamente.", "success")
    return redirect(url_for("samples_bp.samples"))


# ===============================
# ⚡ EVENTOS EN TIEMPO REAL (SSE)
# ===============================
@samples_bp.route("/samples/stream")
def samples_stream():
    def event_stream():
        last_index = 0
        while True:
            if len(SAMPLE_EVENTS) > last_index:
                data = SAMPLE_EVENTS[last_index]
                yield f"data: {data}\n\n"
                last_index += 1
            time.sleep(1)

    return Response(event_stream(), mimetype="text/event-stream")
