import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from db import (
    ejecutar_select,
    ejecutar_insert,
    ejecutar_update,
    registrar_auditoria,
    recalcular_dvv,
    calcular_dvh
)

template_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend", "pages", "samples")
samples_bp = Blueprint("samples_bp", __name__, template_folder=template_dir, static_folder=template_dir)


# ======================================================
# 📋 LISTAR MUESTRAS
# ======================================================
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


# ======================================================
# ➕ CREAR MUESTRA (100% compatible)
# ======================================================
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

    # 1️⃣ Insertar muestra
    new_id = ejecutar_insert("""
        INSERT INTO muestras (nombre, tipo, estado, responsable_id, ubicacion, estado_logico)
        VALUES (?, ?, ?, ?, ?, 0)
    """, (nombre, tipo, estado, responsable_id, ubicacion))

    # 2️⃣ Obtener fila completa recién creada
    fila = ejecutar_select("SELECT * FROM muestras WHERE id = ?", (new_id,))[0]

    # 3️⃣ Convertir fila a dict
    datos_fila = {key: fila[key] for key in fila.keys() if key != "dvh"}

    # 4️⃣ Calcular DVH basado en la fila REAL
    dvh = calcular_dvh(datos_fila)

    # 5️⃣ Guardar DVH en la BD
    ejecutar_update("UPDATE muestras SET dvh = ? WHERE id = ?", (dvh, new_id))

    # 6️⃣ Registrar auditoría (ya calcula su propio DVH)
    registrar_auditoria(responsable_id, "CREAR MUESTRA", "muestras", new_id, request.remote_addr)

    # 7️⃣ Recalcular DVV de toda la tabla
    recalcular_dvv("muestras")

    # 8️⃣ Notificación WebSocket
    from servidor import socketio
    socketio.emit("nuevo_evento", f"Nueva muestra agregada: {nombre}")

    flash("Muestra creada correctamente.", "success")
    return redirect(url_for("samples_bp.samples"))


# ======================================================
# ✏️ ACTUALIZAR MUESTRA
# ======================================================
@samples_bp.route("/samples/update/<int:id>", methods=["POST"])
def update_sample(id):
    nombre = request.form.get("nombre")
    tipo = request.form.get("tipo")
    estado = request.form.get("estado")
    ubicacion = request.form.get("ubicacion")

    # 1️⃣ Actualizar datos
    ejecutar_update(
        "UPDATE muestras SET nombre=?, tipo=?, estado=?, ubicacion=? WHERE id=?",
        (nombre, tipo, estado, ubicacion, id)
    )

    # 2️⃣ Obtener nueva fila
    fila = ejecutar_select("SELECT * FROM muestras WHERE id = ?", (id,))[0]

    # 3️⃣ Crear diccionario sin dvh
    datos_fila = {key: fila[key] for key in fila.keys() if key != "dvh"}

    # 4️⃣ Recalcular DVH
    dvh = calcular_dvh(datos_fila)
    ejecutar_update("UPDATE muestras SET dvh = ? WHERE id = ?", (dvh, id))

    # 5️⃣ Auditoría + DVV
    registrar_auditoria(session["usuario_id"], "ACTUALIZAR MUESTRA", "muestras", id, request.remote_addr)
    recalcular_dvv("muestras")

    # 6️⃣ WebSocket
    from servidor import socketio
    socketio.emit("nuevo_evento", f"Muestra '{nombre}' actualizada.")

    flash("Muestra actualizada correctamente.", "success")
    return redirect(url_for("samples_bp.samples"))


# ======================================================
# 🗑️ ELIMINAR (lógico)
# ======================================================
@samples_bp.route("/samples/delete/<int:id>")
def delete_sample(id):
    # 1️⃣ Marcar como eliminada
    ejecutar_update("UPDATE muestras SET estado_logico=1 WHERE id=?", (id,))

    # 2️⃣ Obtener fila actualizada
    fila = ejecutar_select("SELECT * FROM muestras WHERE id = ?", (id,))[0]

    # 3️⃣ Diccionario sin dvh
    datos_fila = {key: fila[key] for key in fila.keys() if key != "dvh"}

    # 4️⃣ Recalcular DVH
    dvh = calcular_dvh(datos_fila)
    ejecutar_update("UPDATE muestras SET dvh = ? WHERE id = ?", (dvh, id))

    # 5️⃣ Auditoría + DVV
    registrar_auditoria(session["usuario_id"], "ELIMINAR MUESTRA", "muestras", id, request.remote_addr)
    recalcular_dvv("muestras")

    # 6️⃣ WebSocket
    from servidor import socketio
    socketio.emit("nuevo_evento", f"Muestra ID {id} eliminada.")

    flash("Muestra eliminada correctamente.", "success")
    return redirect(url_for("samples_bp.samples"))
