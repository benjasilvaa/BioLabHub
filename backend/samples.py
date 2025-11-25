import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
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
# 📋 LISTAR MUESTRAS (con estadísticas para dashboard)
# ======================================================
@samples_bp.route("/samples")
def samples():
    if "usuario_id" not in session:
        flash("Debes iniciar sesión primero.", "error")
        return redirect(url_for("login_bp.login"))

    usuario_id = session["usuario_id"]

    # -----------------------
    # Listado principal
    # -----------------------
    muestras = ejecutar_select("""
        SELECT m.id, m.nombre, m.tipo, m.estado, m.ubicacion,
               u.nombre AS responsable, m.fecha_ingreso
        FROM muestras m
        LEFT JOIN usuarios u ON m.responsable_id = u.id
        WHERE m.estado_logico = 0
        ORDER BY m.fecha_ingreso DESC
    """)

    laboratorios = ejecutar_select(
        "SELECT nombre FROM laboratorios WHERE estado_logico = 0 ORDER BY nombre ASC"
    )

    # -----------------------
    # Estadísticas dashboard
    # -----------------------
    total_activos = ejecutar_select(
        "SELECT COUNT(*) AS c FROM muestras WHERE estado_logico = 0"
    )[0]["c"]

    en_analisis = ejecutar_select(
        "SELECT COUNT(*) AS c FROM muestras WHERE estado_logico = 0 AND estado = 'En análisis'"
    )[0]["c"]

    en_almacenamiento = ejecutar_select(
        "SELECT COUNT(*) AS c FROM muestras WHERE estado_logico = 0 AND estado = 'En almacenamiento'"
    )[0]["c"]

    descartadas = ejecutar_select(
        "SELECT COUNT(*) AS c FROM muestras WHERE estado_logico = 0 AND estado = 'Descartada'"
    )[0]["c"]

    # Muestras creadas por el usuario
    mis_muestras = ejecutar_select(
        "SELECT COUNT(*) AS c FROM muestras WHERE estado_logico = 0 AND responsable_id = ?",
        (usuario_id,),
    )[0]["c"]

    stats = {
        "total_activos": total_activos,
        "en_analisis": en_analisis,
        "en_almacenamiento": en_almacenamiento,
        "descartadas": descartadas,
        "mis_muestras": mis_muestras
    }

    return render_template("samples/samples.html",
                           muestras=muestras,
                           laboratorios=laboratorios,
                           stats=stats)


# ======================================================
# 🔍 📄 DETALLE DE MUESTRA (para modal)
# ======================================================
@samples_bp.route("/samples/detail/<int:id>")
def sample_detail(id):

    sample = ejecutar_select("""
        SELECT id, nombre, tipo, estado, ubicacion, fecha_ingreso,
               responsable_id,
               origen, condiciones, observaciones
        FROM muestras
        WHERE id = ? AND estado_logico = 0
    """, (id,))

    if not sample:
        return jsonify({"error": "Muestra no encontrada"}), 404

    return jsonify(sample[0])


# ======================================================
# ➕ CREAR MUESTRA
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

    # 2️⃣ Obtener fila completa
    fila = ejecutar_select("SELECT * FROM muestras WHERE id = ?", (new_id,))[0]

    # 3️⃣ Diccionario sin DVH
    datos_fila = {k: fila[k] for k in fila.keys() if k != "dvh"}

    # 4️⃣ Calcular DVH
    dvh = calcular_dvh(datos_fila)
    ejecutar_update("UPDATE muestras SET dvh = ? WHERE id = ?", (dvh, new_id))

    # 5️⃣ Auditoría
    registrar_auditoria(responsable_id, "CREAR MUESTRA", "muestras", new_id, request.remote_addr)

    # 6️⃣ DVV
    recalcular_dvv("muestras")

    # 7️⃣ WebSocket
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

    # 1️⃣ Actualizar
    ejecutar_update("""
        UPDATE muestras
        SET nombre=?, tipo=?, estado=?, ubicacion=?
        WHERE id=?
    """, (nombre, tipo, estado, ubicacion, id))

    # 2️⃣ Releer fila
    fila = ejecutar_select("SELECT * FROM muestras WHERE id = ?", (id,))[0]

    datos_fila = {k: fila[k] for k in fila.keys() if k != "dvh"}

    # 3️⃣ DVH
    dvh = calcular_dvh(datos_fila)
    ejecutar_update("UPDATE muestras SET dvh = ? WHERE id = ?", (dvh, id))

    # 4️⃣ Auditoría + DVV
    registrar_auditoria(session["usuario_id"], "ACTUALIZAR MUESTRA", "muestras", id, request.remote_addr)
    recalcular_dvv("muestras")

    # 5️⃣ WebSocket
    from servidor import socketio
    socketio.emit("nuevo_evento", f"Muestra '{nombre}' actualizada.")

    flash("Muestra actualizada correctamente.", "success")
    return redirect(url_for("samples_bp.samples"))


# ======================================================
# 🗑️ ELIMINAR LÓGICO
# ======================================================
@samples_bp.route("/samples/delete/<int:id>")
def delete_sample(id):

    # 1️⃣ Marcar como eliminada
    ejecutar_update("UPDATE muestras SET estado_logico=1 WHERE id=?", (id,))

    # 2️⃣ Releer fila
    fila = ejecutar_select("SELECT * FROM muestras WHERE id = ?", (id,))[0]

    datos_fila = {k: fila[k] for k in fila.keys() if k != "dvh"}

    # 3️⃣ DVH
    dvh = calcular_dvh(datos_fila)
    ejecutar_update("UPDATE muestras SET dvh = ? WHERE id = ?", (dvh, id))

    # 4️⃣ Auditoría + DVV
    registrar_auditoria(session["usuario_id"], "ELIMINAR MUESTRA", "muestras", id, request.remote_addr)
    recalcular_dvv("muestras")

    # 5️⃣ WebSocket
    from servidor import socketio
    socketio.emit("nuevo_evento", f"Muestra ID {id} eliminada.")

    flash("Muestra eliminada correctamente.", "success")
    return redirect(url_for("samples_bp.samples"))
