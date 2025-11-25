from flask import Blueprint, render_template, request, redirect, url_for, flash, session, send_from_directory, jsonify
import os
import sqlite3
from werkzeug.utils import secure_filename

# 🔐 Importamos funciones de auditoría e integridad
from db import (
    registrar_auditoria,
    calcular_dvh,
    recalcular_dvv,
    ejecutar_select,
    ejecutar_insert,
    ejecutar_update,
    conectar_bd as conectar_principal_bd
)

experiments_bp = Blueprint("experiments_bp", __name__, url_prefix="/experiments")

# Ruta donde se guardan archivos
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "..", "uploads", "protocolos")

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# ---------------------------
#  FUNCIONES DE BASE DE DATOS (internas)
# ---------------------------

def conectar_bd():
    ruta = os.path.join(BASE_DIR, "..", "biolabhub.db")
    conn = sqlite3.connect(ruta)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------
#  LISTAR EXPERIMENTOS
# ---------------------------

@experiments_bp.route("/")
def experiments():
    if "usuario_id" not in session:
        flash("Debes iniciar sesión.", "error")
        return redirect(url_for("login_bp.login"))

    conn = conectar_bd()
    cur = conn.cursor()

    # Experimentos
    cur.execute("""
        SELECT e.id, e.titulo, e.descripcion, e.fecha_inicio, e.fecha_fin, 
               e.estado, e.protocolo_archivo, u.nombre AS responsable
        FROM experimentos e
        LEFT JOIN usuarios u ON e.responsable_id = u.id
        ORDER BY e.id DESC
    """)
    experimentos = cur.fetchall()

    # Usuarios (para admin)
    cur.execute("SELECT id, nombre FROM usuarios")
    usuarios = cur.fetchall()

    conn.close()

    return render_template(
        "experiments/Experiments.html",
        experimentos=experimentos,
        usuarios=usuarios
    )


# ---------------------------
#  AGREGAR EXPERIMENTO
# ---------------------------

@experiments_bp.route("/add", methods=["POST"])
def add_experiment():
    titulo = request.form.get("titulo")
    descripcion = request.form.get("descripcion")
    fecha_inicio = request.form.get("fecha_inicio")
    fecha_fin = request.form.get("fecha_fin")
    estado = request.form.get("estado")
    responsable = request.form.get("responsable") or None

    archivo = request.files.get("protocolo")
    archivo_nombre = None

    # Guardar archivo si existe
    if archivo and archivo.filename:
        archivo_nombre = secure_filename(archivo.filename)
        archivo.save(os.path.join(UPLOAD_FOLDER, archivo_nombre))

    conn = conectar_bd()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO experimentos 
        (titulo, descripcion, fecha_inicio, fecha_fin, estado, responsable_id, protocolo_archivo, dvh)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        titulo,
        descripcion,
        fecha_inicio,
        fecha_fin,
        estado,
        responsable,
        archivo_nombre,
        0  # placeholder
    ))
    conn.commit()

    nuevo_id = cur.lastrowid
    conn.close()

    # 🧮 Recalcular DVH del nuevo registro
    datos_experimento = {
        "titulo": titulo,
        "descripcion": descripcion,
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
        "estado": estado,
        "responsable_id": responsable,
        "protocolo_archivo": archivo_nombre
    }
    dvh_nuevo = sum(len(str(v)) for v in datos_experimento.values())

    conn = conectar_bd()
    cur = conn.cursor()
    cur.execute("UPDATE experimentos SET dvh = ? WHERE id = ?", (dvh_nuevo, nuevo_id))
    conn.commit()
    conn.close()

    # 🔄 Actualizar DVV
    recalcular_dvv("experimentos")

    # 📝 Registrar auditoría
    registrar_auditoria(
        usuario_id=session.get("usuario_id"),
        accion="CREAR EXPERIMENTO",
        tabla="experimentos",
        registro_id=nuevo_id,
        ip_origen=request.remote_addr
    )

    # 🎯 WebSocket
    from servidor import socketio
    socketio.emit("experiment_event", f"🧪 Nuevo experimento creado: {titulo}")

    flash("Experimento agregado correctamente.", "success")
    return redirect(url_for("experiments_bp.experiments"))


# ---------------------------
#  ELIMINAR EXPERIMENTO
# ---------------------------

@experiments_bp.route("/delete/<int:id>")
def delete_experiment(id):
    conn = conectar_bd()
    cur = conn.cursor()

    # Obtener nombre para el evento
    cur.execute("SELECT titulo FROM experimentos WHERE id = ?", (id,))
    row = cur.fetchone()
    titulo = row["titulo"] if row else "(desconocido)"

    # Borrado lógico (si querés mantener DVH)
    cur.execute("UPDATE experimentos SET estado_logico = 1 WHERE id = ?", (id,))
    conn.commit()
    conn.close()

    # DVV se actualiza igual
    recalcular_dvv("experimentos")

    # Auditoría
    registrar_auditoria(
        usuario_id=session.get("usuario_id"),
        accion="BORRAR EXPERIMENTO",
        tabla="experimentos",
        registro_id=id,
        ip_origen=request.remote_addr
    )

    # 🎯 WebSocket
    from servidor import socketio
    socketio.emit("experiment_event", f"🗑️ Experimento eliminado: {titulo}")

    flash("Experimento eliminado correctamente.", "success")
    return redirect(url_for("experiments_bp.experiments"))


# ---------------------------
#  DESCARGAR PROTOCOLO
# ---------------------------

@experiments_bp.route("/protocolo/<path:filename>")
def descargar_protocolo(filename):
    return send_from_directory(UPLOAD_FOLDER, filename, as_attachment=True)


# ---------------------------
#  EVENTOS PARA FULLCALENDAR
# ---------------------------

@experiments_bp.route("/events")
def experiments_events():
    conn = conectar_bd()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, titulo, descripcion, fecha_inicio, fecha_fin
        FROM experimentos
        WHERE estado_logico = 0 OR estado_logico IS NULL
    """)
    rows = cur.fetchall()
    conn.close()

    eventos = []
    for r in rows:
        eventos.append({
            "id": r["id"],
            "title": r["titulo"],
            "start": r["fecha_inicio"],
            "end": r["fecha_fin"],
            "description": r["descripcion"]
        })

    return jsonify(eventos)
