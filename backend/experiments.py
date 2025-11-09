import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, send_from_directory
from db import ejecutar_select, ejecutar_insert, ejecutar_update, registrar_auditoria, recalcular_dvv
from datetime import datetime, timedelta
import random

# Ruta a las plantillas de experimentos
template_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend", "pages", "experiments")
upload_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "uploads", "protocolos")
os.makedirs(upload_dir, exist_ok=True)

# Blueprint de Experiment Planner
experiments_bp = Blueprint("experiments_bp", __name__, template_folder=template_dir, static_folder=template_dir)


# 📋 Mostrar experimentos
@experiments_bp.route("/experiments", methods=["GET"])
def experiments():
    if "usuario_id" not in session:
        flash("Debes iniciar sesión primero.", "error")
        return redirect(url_for("login_bp.login"))

    query = """
        SELECT e.id, e.titulo, e.descripcion, e.fecha_inicio, e.fecha_fin,
               e.estado, u.nombre AS responsable, e.protocolo_archivo
        FROM experimentos e
        LEFT JOIN usuarios u ON e.responsable_id = u.id
        WHERE e.estado_logico = 0
        ORDER BY e.fecha_inicio DESC
    """
    experimentos = ejecutar_select(query)
    return render_template("experiments/experiments.html", experimentos=experimentos, usuario=session["nombre"])


# 🧪 Agregar nuevo experimento (con protocolo opcional)
@experiments_bp.route("/experiments/add", methods=["POST"])
def add_experiment():
    if "usuario_id" not in session:
        flash("Inicia sesión primero.", "error")
        return redirect(url_for("login_bp.login"))

    titulo = request.form.get("titulo")
    descripcion = request.form.get("descripcion")
    fecha_inicio = request.form.get("fecha_inicio")
    fecha_fin = request.form.get("fecha_fin")
    estado = request.form.get("estado", "Planificado")
    responsable_id = session["usuario_id"]

    if not titulo or not descripcion:
        flash("Por favor, completa todos los campos obligatorios.", "error")
        return redirect(url_for("experiments_bp.experiments"))

    # Manejo del archivo (protocolo)
    protocolo_filename = None
    if "protocolo" in request.files:
        file = request.files["protocolo"]
        if file and file.filename != "":
            nombre_archivo = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}"
            file.save(os.path.join(upload_dir, nombre_archivo))
            protocolo_filename = nombre_archivo

    query = """
        INSERT INTO experimentos (titulo, descripcion, responsable_id, fecha_inicio, fecha_fin, estado, estado_logico, protocolo_archivo)
        VALUES (?, ?, ?, ?, ?, ?, 0, ?)
    """
    new_id = ejecutar_insert(query, (titulo, descripcion, responsable_id, fecha_inicio, fecha_fin, estado, protocolo_filename))

    registrar_auditoria(session["usuario_id"], "CREAR EXPERIMENTO", "experimentos", new_id, request.remote_addr)
    recalcular_dvv("experimentos")

    flash("✅ Experimento agregado correctamente.", "success")
    return redirect(url_for("experiments_bp.experiments"))


# 🗑️ Eliminar experimento
@experiments_bp.route("/experiments/delete/<int:id>")
def delete_experiment(id):
    ejecutar_update("UPDATE experimentos SET estado_logico = 1 WHERE id = ?", (id,))
    registrar_auditoria(session.get("usuario_id"), "ELIMINAR EXPERIMENTO", "experimentos", id, request.remote_addr)
    recalcular_dvv("experimentos")

    flash("🗑️ Experimento eliminado correctamente.", "success")
    return redirect(url_for("experiments_bp.experiments"))


# ✏️ Actualizar experimento
@experiments_bp.route("/experiments/update/<int:id>", methods=["POST"])
def update_experiment(id):
    titulo = request.form.get("titulo")
    descripcion = request.form.get("descripcion")
    fecha_inicio = request.form.get("fecha_inicio")
    fecha_fin = request.form.get("fecha_fin")
    estado = request.form.get("estado")

    query = """
        UPDATE experimentos
        SET titulo = ?, descripcion = ?, fecha_inicio = ?, fecha_fin = ?, estado = ?
        WHERE id = ?
    """
    ejecutar_update(query, (titulo, descripcion, fecha_inicio, fecha_fin, estado, id))

    registrar_auditoria(session.get("usuario_id"), "ACTUALIZAR EXPERIMENTO", "experimentos", id, request.remote_addr)
    recalcular_dvv("experimentos")

    flash("✏️ Experimento actualizado correctamente.", "success")
    return redirect(url_for("experiments_bp.experiments"))


# 📎 Descargar protocolo
@experiments_bp.route("/experiments/protocolo/<filename>")
def descargar_protocolo(filename):
    try:
        return send_from_directory(upload_dir, filename, as_attachment=True)
    except FileNotFoundError:
        flash("El archivo no existe o fue eliminado.", "error")
        return redirect(url_for("experiments_bp.experiments"))


# 📅 Endpoint JSON para el calendario
@experiments_bp.route("/events")
def experiments_events():
    experimentos = ejecutar_select("SELECT * FROM experimentos WHERE estado_logico = 0")
    eventos = []

    colores = [
        "#007BFF", "#28A745", "#FFC107", "#DC3545", "#6F42C1", "#20C997",
        "#FD7E14", "#6610F2", "#E83E8C", "#17A2B8"
    ]

    for exp in experimentos:
        fecha_inicio = exp["fecha_inicio"]
        fecha_fin = exp["fecha_fin"]

        if fecha_fin:
            try:
                fecha_fin = (datetime.strptime(fecha_fin, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
            except Exception:
                pass

        color = random.choice(colores)

        eventos.append({
            "id": exp["id"],
            "title": exp["titulo"],
            "start": fecha_inicio,
            "end": fecha_fin,
            "description": exp["descripcion"],
            "color": color,
            "textColor": "#fff"
        })

    return jsonify(eventos)
