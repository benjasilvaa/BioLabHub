from flask import Blueprint, render_template, request, redirect, url_for, flash, session, send_from_directory, jsonify
import os
import sqlite3
from werkzeug.utils import secure_filename

from db import (
    registrar_auditoria,
    recalcular_dvv,
)

experiments_bp = Blueprint("experiments_bp", __name__, url_prefix="/experiments")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "..", "uploads", "protocolos")

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# -----------------------------
# CONEXIÓN SEGURA PARA CADA HILO
# -----------------------------
def conectar_bd():
    ruta = os.path.join(BASE_DIR, "..", "biolabhub.db")
    conn = sqlite3.connect(ruta)
    conn.row_factory = sqlite3.Row
    return conn



def post_proceso_experimento(accion, registro_id, datos, ip, usuario_id):
    
    try:
       
        from servidor import socketio

        conn = conectar_bd()
        conn.close()

        recalcular_dvv("experimentos")

        registrar_auditoria(
            usuario_id=usuario_id,
            accion=accion,
            tabla="experimentos",
            registro_id=registro_id,
            ip_origen=ip,
        )

       
        texto = f"{accion}: {datos.get('titulo', '(sin título)')}"

        
        try:
            socketio.emit("experiment_event", texto)
        except Exception as e:
            print("Error emitiendo 'experiment_event':", e)

        
        try:
            print("EMITIENDO EVENTO a admin panel:", texto)
            socketio.emit("experimento_actualizado", {"mensaje": texto} )
        except Exception as e:
            print("Error emitiendo 'experimento_actualizado':", e)

    except Exception as e:
        print("Error en hilo post-proceso:", e)


# -----------------------------
# LISTADO
# -----------------------------
@experiments_bp.route("/")
def experiments():
    if "usuario_id" not in session:
        flash("Debes iniciar sesión.", "error")
        return redirect(url_for("login_bp.login"))

    conn = conectar_bd()
    cur = conn.cursor()

    cur.execute("""
        SELECT e.id, e.titulo, e.descripcion, e.fecha_inicio, e.fecha_fin, 
               e.estado, e.protocolo_archivo, u.nombre AS responsable, e.responsable_id
        FROM experimentos e
        LEFT JOIN usuarios u ON e.responsable_id = u.id
        WHERE e.estado_logico = 0 OR e.estado_logico IS NULL
        ORDER BY e.id DESC
    """)
    experimentos = cur.fetchall()

    usuarios = []
    if session.get("rol") == "admin":
        cur.execute("SELECT id, nombre FROM usuarios WHERE estado_logico = 0 OR estado_logico IS NULL ORDER BY nombre ASC")
        usuarios = cur.fetchall()

    conn.close()

    return render_template(
        "experiments/Experiments.html",
        experimentos=experimentos,
        usuarios=usuarios
    )


# -----------------------------
# AGREGAR
# -----------------------------
@experiments_bp.route("/add", methods=["POST"])
def add_experiment():
    from servidor import lanzar_tarea_en_segundo_plano

    titulo = request.form.get("titulo")
    descripcion = request.form.get("descripcion")
    fecha_inicio = request.form.get("fecha_inicio")
    fecha_fin = request.form.get("fecha_fin")
    estado = request.form.get("estado")

    if session.get("rol") != "admin":
        responsable = session.get("usuario_id")
    else:
        responsable = request.form.get("responsable") or None

    archivo = request.files.get("protocolo")
    archivo_nombre = None

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
        0
    ))

    conn.commit()
    nuevo_id = cur.lastrowid
    conn.close()

    datos = {
        "titulo": titulo,
        "descripcion": descripcion,
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
        "estado": estado,
        "responsable_id": responsable,
        "protocolo_archivo": archivo_nombre
    }

    dvh = sum(len(str(v)) for v in datos.values())

    conn = conectar_bd()
    cur = conn.cursor()
    cur.execute("UPDATE experimentos SET dvh = ? WHERE id = ?", (dvh, nuevo_id))
    conn.commit()
    conn.close()

    lanzar_tarea_en_segundo_plano(
        post_proceso_experimento,
        "CREAR EXPERIMENTO",
        nuevo_id,
        datos,
        request.remote_addr,
        session.get("usuario_id")
    )

    flash("Experimento agregado correctamente.", "success")
    return redirect(url_for("experiments_bp.experiments"))



@experiments_bp.route("/get/<int:id>")
def get_experiment(id):
    if "usuario_id" not in session:
        return jsonify({"error": "No autenticado."}), 401

    conn = conectar_bd()
    cur = conn.cursor()

    cur.execute("""
        SELECT id, titulo, descripcion, fecha_inicio, fecha_fin, estado, protocolo_archivo, responsable_id
        FROM experimentos
        WHERE id = ? AND (estado_logico = 0 OR estado_logico IS NULL)
    """, (id,))
    row = cur.fetchone()

    if not row:
        conn.close()
        return jsonify({"error": "Experimento no encontrado."}), 404

    if session.get("rol") != "admin" and row["responsable_id"] != session.get("usuario_id"):
        conn.close()
        return jsonify({"error": "No tenés permisos para editar este experimento."}), 403

    usuarios = []
    if session.get("rol") == "admin":
        cur.execute("SELECT id, nombre FROM usuarios WHERE estado_logico = 0 OR estado_logico IS NULL ORDER BY nombre ASC")
        usuarios = [dict(u) for u in cur.fetchall()]

    exp = dict(row)
    conn.close()

    return jsonify({"experimento": exp, "usuarios": usuarios}), 200



@experiments_bp.route("/update/<int:id>", methods=["POST"])
def update_experiment(id):
    from servidor import lanzar_tarea_en_segundo_plano

    if "usuario_id" not in session:
        flash("Debes iniciar sesión.", "error")
        return redirect(url_for("login_bp.login"))

    conn = conectar_bd()
    cur = conn.cursor()

    cur.execute("SELECT * FROM experimentos WHERE id = ?", (id,))
    row = cur.fetchone()

    if not row:
        conn.close()
        flash("Experimento no encontrado.", "error")
        return redirect(url_for("experiments_bp.experiments"))

    if session.get("rol") != "admin" and row["responsable_id"] != session.get("usuario_id"):
        conn.close()
        flash("No tenés permiso para editar este experimento.", "error")
        return redirect(url_for("experiments_bp.experiments"))

    titulo = request.form.get("titulo")
    descripcion = request.form.get("descripcion")
    fecha_inicio = request.form.get("fecha_inicio")
    fecha_fin = request.form.get("fecha_fin")
    estado = request.form.get("estado")

    if session.get("rol") == "admin":
        responsable = request.form.get("responsable") or None
    else:
        responsable = row["responsable_id"]

    archivo = request.files.get("protocolo")
    protocolo_nombre = row["protocolo_archivo"]

    if archivo and archivo.filename:
        protocolo_nombre = secure_filename(archivo.filename)
        archivo.save(os.path.join(UPLOAD_FOLDER, protocolo_nombre))

    cur.execute("""
        UPDATE experimentos
        SET titulo = ?, descripcion = ?, fecha_inicio = ?, fecha_fin = ?, estado = ?, responsable_id = ?, protocolo_archivo = ?
        WHERE id = ?
    """, (titulo, descripcion, fecha_inicio, fecha_fin, estado, responsable, protocolo_nombre, id))

    conn.commit()

    datos = {
        "titulo": titulo,
        "descripcion": descripcion,
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
        "estado": estado,
        "responsable_id": responsable,
        "protocolo_archivo": protocolo_nombre
    }

    dvh = sum(len(str(v)) for v in datos.values())

    cur.execute("UPDATE experimentos SET dvh = ? WHERE id = ?", (dvh, id))
    conn.commit()
    conn.close()

    lanzar_tarea_en_segundo_plano(
        post_proceso_experimento,
        "EDITAR EXPERIMENTO",
        id,
        datos,
        request.remote_addr,
        session.get("usuario_id")
    )

    flash("Experimento actualizado correctamente.", "success")
    return redirect(url_for("experiments_bp.experiments"))



@experiments_bp.route("/delete/<int:id>")
def delete_experiment(id):
    from servidor import lanzar_tarea_en_segundo_plano

    conn = conectar_bd()
    cur = conn.cursor()

    cur.execute("SELECT titulo FROM experimentos WHERE id = ?", (id,))
    row = cur.fetchone()
    titulo = row["titulo"] if row else "(desconocido)"

    cur.execute("UPDATE experimentos SET estado_logico = 1 WHERE id = ?", (id,))
    conn.commit()
    conn.close()

    datos = {"titulo": titulo}

    lanzar_tarea_en_segundo_plano(
        post_proceso_experimento,
        "BORRAR EXPERIMENTO",
        id,
        datos,
        request.remote_addr,
        session.get("usuario_id")
    )

    flash("Experimento eliminado correctamente.", "success")
    return redirect(url_for("experiments_bp.experiments"))



@experiments_bp.route("/protocolo/<path:filename>")
def descargar_protocolo(filename):
    return send_from_directory(UPLOAD_FOLDER, filename, as_attachment=True)



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
