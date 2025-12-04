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

def post_proceso_muestra(accion, muestra_id, datos, ip, usuario_id):
    try:
        from servidor import socketio
        registrar_auditoria(
            usuario_id,
            accion,
            "muestras",
            muestra_id,
            ip,
        )
        recalcular_dvv("muestras")
        nombre = datos.get("nombre") or f"ID {muestra_id}"
        if accion == "CREAR MUESTRA":
            texto = f"Nueva muestra agregada: {nombre}"
        elif accion == "ACTUALIZAR MUESTRA":
            texto = f"Muestra '{nombre}' actualizada."
        elif accion == "ELIMINAR MUESTRA":
            texto = f"Muestra ID {muestra_id} eliminada."
        else:
            texto = f"Acción sobre muestra ({accion}): {nombre}"
        socketio.emit("nuevo_evento", texto)
    except Exception as e:
        print(f"Error en proceso posterior de muestra: {e}")

@samples_bp.route("/samples")
def samples():
    if "usuario_id" not in session:
        flash("Debes iniciar sesión primero.", "error")
        return redirect(url_for("login_bp.login"))
    usuario_id = session["usuario_id"]
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
    fila = ejecutar_select("SELECT * FROM muestras WHERE id = ?", (new_id,))[0]
    datos_fila = {k: fila[k] for k in fila.keys() if k != "dvh"}
    dvh = calcular_dvh(datos_fila)
    ejecutar_update("UPDATE muestras SET dvh = ? WHERE id = ?", (dvh, new_id))
    datos_muestra = {"nombre": nombre}
    from servidor import lanzar_tarea_en_segundo_plano
    lanzar_tarea_en_segundo_plano(
        post_proceso_muestra,
        "CREAR MUESTRA",
        new_id,
        datos_muestra,
        request.remote_addr,
        responsable_id,
    )

    flash("Muestra creada correctamente.", "success")
    return redirect(url_for("samples_bp.samples"))

@samples_bp.route("/samples/update/<int:id>", methods=["POST"])
def update_sample(id):
    nombre = request.form.get("nombre")
    tipo = request.form.get("tipo")
    estado = request.form.get("estado")
    ubicacion = request.form.get("ubicacion")
    ejecutar_update("""
        UPDATE muestras
        SET nombre=?, tipo=?, estado=?, ubicacion=?
        WHERE id=?
    """, (nombre, tipo, estado, ubicacion, id))
    fila = ejecutar_select("SELECT * FROM muestras WHERE id = ?", (id,))[0]
    datos_fila = {k: fila[k] for k in fila.keys() if k != "dvh"}
    dvh = calcular_dvh(datos_fila)
    ejecutar_update("UPDATE muestras SET dvh = ? WHERE id = ?", (dvh, id))
    datos_muestra = {"nombre": nombre}
    from servidor import lanzar_tarea_en_segundo_plano
    lanzar_tarea_en_segundo_plano(
        post_proceso_muestra,
        "ACTUALIZAR MUESTRA",
        id,
        datos_muestra,
        request.remote_addr,
        session["usuario_id"],
    )

    flash("Muestra actualizada correctamente.", "success")
    return redirect(url_for("samples_bp.samples"))

@samples_bp.route("/samples/delete/<int:id>")
def delete_sample(id):
    ejecutar_update("UPDATE muestras SET estado_logico=1 WHERE id=?", (id,))
    fila = ejecutar_select("SELECT * FROM muestras WHERE id = ?", (id,))[0]
    datos_fila = {k: fila[k] for k in fila.keys() if k != "dvh"}
    dvh = calcular_dvh(datos_fila)
    ejecutar_update("UPDATE muestras SET dvh = ? WHERE id = ?", (dvh, id))
    datos_muestra = {"nombre": fila.get("nombre") if hasattr(fila, "get") else fila["nombre"]}
    from servidor import lanzar_tarea_en_segundo_plano
    lanzar_tarea_en_segundo_plano(
        post_proceso_muestra,
        "ELIMINAR MUESTRA",
        id,
        datos_muestra,
        request.remote_addr,
        session["usuario_id"],
    )

    flash("Muestra eliminada correctamente.", "success")
    return redirect(url_for("samples_bp.samples"))