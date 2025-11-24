import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from db import ejecutar_select, ejecutar_insert, ejecutar_update, registrar_auditoria, recalcular_dvv

template_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend", "pages", "samples")
samples_bp = Blueprint("samples_bp", __name__, template_folder=template_dir, static_folder=template_dir)


# ===============================
# 📋 LISTAR MUESTRAS
# ===============================
@samples_bp.route("/samples")
def samples():
    if "usuario_id" not in session:
        flash("Debes iniciar sesión primero.", "error")
        return redirect(url_for("login_bp.login"))

    muestras = ejecutar_select("""
        SELECT m.id, m.nombre, m.tipo, m.estado, m.ubicacion, u.nombre AS responsable
        FROM muestras m
        LEFT JOIN usuarios u ON m.responsable_id = u.id
        WHERE m.estado_logico = 0
        ORDER BY m.fecha_ingreso DESC
    """)

    laboratorios = ejecutar_select("SELECT nombre FROM laboratorios WHERE estado_logico = 0 ORDER BY nombre ASC")

    return render_template("samples/samples.html", muestras=muestras, laboratorios=laboratorios)


# ===============================
# ➕ CREAR MUESTRA
# ===============================
@samples_bp.route("/samples/add", methods=["POST"])
def add_sample():
    if "usuario_id" not in session:
        flash("Debes iniciar sesión primero.", "error")
        return redirect(url_for("login_bp.login"))

    nombre = request.form.get("nombre")
    tipo = request.form.get("tipo")
    estado = request.form.get("estado")
    ubicacion = request.form.get("ubicacion")

    responsable_id = session["usuario_id"]

    new_id = ejecutar_insert("""
        INSERT INTO muestras (nombre, tipo, estado, responsable_id, ubicacion, estado_logico)
        VALUES (?, ?, ?, ?, ?, 0)
    """, (nombre, tipo, estado, responsable_id, ubicacion))

    registrar_auditoria(responsable_id, "CREAR MUESTRA", "muestras", new_id, request.remote_addr)
    recalcular_dvv("muestras")

    # 👉 import acá (NO arriba del archivo)
    from servidor import socketio
    socketio.emit("nuevo_evento", f"Nueva muestra agregada: {nombre}")

    flash("Muestra creada correctamente.", "success")
    return redirect(url_for("samples_bp.samples"))


# ===============================
# ✏️ ACTUALIZAR
# ===============================
@samples_bp.route("/samples/update/<int:id>", methods=["POST"])
def update_sample(id):
    nombre = request.form.get("nombre")
    tipo = request.form.get("tipo")
    estado = request.form.get("estado")
    ubicacion = request.form.get("ubicacion")

    ejecutar_update(
        "UPDATE muestras SET nombre=?, tipo=?, estado=?, ubicacion=? WHERE id=?",
        (nombre, tipo, estado, ubicacion, id)
    )

    registrar_auditoria(session["usuario_id"], "ACTUALIZAR MUESTRA", "muestras", id, request.remote_addr)
    recalcular_dvv("muestras")

    from servidor import socketio
    socketio.emit("nuevo_evento", f"Muestra '{nombre}' actualizada.")

    flash("Muestra actualizada correctamente.", "success")
    return redirect(url_for("samples_bp.samples"))


# ===============================
# 🗑️ ELIMINAR
# ===============================
@samples_bp.route("/samples/delete/<int:id>")
def delete_sample(id):
    ejecutar_update("UPDATE muestras SET estado_logico=1 WHERE id=?", (id,))

    registrar_auditoria(session["usuario_id"], "ELIMINAR MUESTRA", "muestras", id, request.remote_addr)
    recalcular_dvv("muestras")

    from servidor import socketio
    socketio.emit("nuevo_evento", f"Muestra ID {id} eliminada.")

    flash("Muestra eliminada correctamente.", "success")
    return redirect(url_for("samples_bp.samples"))
