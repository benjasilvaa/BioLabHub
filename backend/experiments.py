from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, 
    session, send_from_directory, jsonify
)
import os
import sqlite3
from werkzeug.utils import secure_filename
from db import registrar_auditoria, recalcular_dvv
experiments_bp = Blueprint("experiments_bp", __name__, url_prefix="/experiments")
# Configuración de rutas
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "..", "uploads", "protocolos")
# Asegurar que exista la carpeta para subir archivos
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
# -----------------------------
# CONEXIÓN SEGURA PARA CADA HILO
# -----------------------------
def conectar_bd():
    """Establece conexión con la base de datos SQLite.
    Returns:
        sqlite3.Connection: Objeto de conexión a la base de datos
    """
    ruta = os.path.join(BASE_DIR, "..", "biolabhub.db")
    conn = sqlite3.connect(ruta)
    conn.row_factory = sqlite3.Row
    return conn
def post_proceso_experimento(accion, registro_id, datos, ip, usuario_id):
    """Procesos posteriores a la creación/actualización de un experimento.
    Args:
        accion (str): Acción realizada (ej: 'CREAR EXPERIMENTO')
        registro_id (int): ID del experimento
        datos (dict): Datos del experimento
        ip (str): Dirección IP de origen
        usuario_id (int): ID del usuario que realizó la acción
    """
    try:
        from servidor import socketio
        # Cerrar cualquier conexión pendiente
        conn = conectar_bd()
        conn.close()
        # Recalcular dígito verificador vertical
        recalcular_dvv("experimentos")
        # Registrar acción en auditoría
        registrar_auditoria(
            usuario_id=usuario_id,
            accion=accion,
            tabla="experimentos",
            registro_id=registro_id,
            ip_origen=ip,
        )
        # Notificar a través de WebSocket
        texto = f"{accion}: {datos.get('titulo', '(sin título)')}"
        # Emitir eventos a los clientes conectados
        try:
            socketio.emit("experiment_event", texto)
            socketio.emit("experimento_actualizado", {"mensaje": texto})
        except Exception as e:
            print(f"Error emitiendo eventos de WebSocket: {e}")
    except Exception as e:
        print(f"Error en proceso posterior al experimento: {e}")
# -----------------------------
# LISTADO
# -----------------------------
@experiments_bp.route("/")
def experiments():
    """Muestra el listado de experimentos.
    Returns:
        str: Renderizado de la plantilla HTML con los experimentos
    """
    if "usuario_id" not in session:
        flash("Debes iniciar sesión para acceder a esta sección.", "error")
        return redirect(url_for("login_bp.login"))
    conn = conectar_bd()
    cur = conn.cursor()
    # Obtener lista de experimentos activos
    cur.execute("""
        SELECT 
            e.id, e.titulo, e.descripcion, 
            e.fecha_inicio, e.fecha_fin, 
            e.estado, e.protocolo_archivo, 
            u.nombre AS responsable, 
            e.responsable_id
        FROM experimentos e
        LEFT JOIN usuarios u ON e.responsable_id = u.id
        WHERE e.estado_logico = 0 OR e.estado_logico IS NULL
        ORDER BY e.id DESC
    """)
    experimentos = cur.fetchall()
    # Si es administrador, cargar lista de usuarios para asignar responsables
    usuarios = []
    if session.get("rol") == "admin":
        cur.execute("""
            SELECT id, nombre 
            FROM usuarios 
            WHERE estado_logico = 0 OR estado_logico IS NULL 
            ORDER BY nombre ASC
        """)
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
    """Agrega un nuevo experimento al sistema.
    Returns:
        Response: Redirección al listado de experimentos
    """
    from servidor import lanzar_tarea_en_segundo_plano
    # Obtener datos del formulario
    titulo = request.form.get("titulo")
    descripcion = request.form.get("descripcion")
    fecha_inicio = request.form.get("fecha_inicio")
    fecha_fin = request.form.get("fecha_fin")
    estado = request.form.get("estado")
    # Validar que la fecha de inicio no sea anterior a la actual
    if fecha_inicio:
        from datetime import datetime
        try:
            fecha_inicio_dt = datetime.strptime(fecha_inicio, "%Y-%m-%d").date()
            if fecha_inicio_dt < datetime.now().date():
                flash("No puedes hacer reservas en fechas pasadas.", "error")
                return redirect(url_for("experiments_bp.experiments"))
        except ValueError:
            flash("Formato de fecha inválido.", "error")
            return redirect(url_for("experiments_bp.experiments"))
    # Determinar el responsable del experimento
    if session.get("rol") != "admin":
        responsable = session.get("usuario_id")
    else:
        responsable = request.form.get("responsable") or None
    # Manejo de archivo de protocolo
    archivo = request.files.get("protocolo")
    archivo_nombre = None
    if archivo and archivo.filename:
        archivo_nombre = secure_filename(archivo.filename)
        try:
            archivo.save(os.path.join(UPLOAD_FOLDER, archivo_nombre))
        except Exception as e:
            flash(f"Error al guardar el archivo: {str(e)}", "error")
            return redirect(url_for("experiments_bp.experiments"))
    # Insertar el experimento en la base de datos
    conn = conectar_bd()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO experimentos 
            (titulo, descripcion, fecha_inicio, fecha_fin, estado, 
             responsable_id, protocolo_archivo, dvh)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            titulo,
            descripcion,
            fecha_inicio,
            fecha_fin,
            estado,
            responsable,
            archivo_nombre,
            0  # DVH temporal
        ))
        nuevo_id = cur.lastrowid
        conn.commit()
        # Calcular y actualizar DVH
        datos = {
            "titulo": titulo,
            "descripcion": descripcion,
            "fecha_inicio": fecha_inicio,
            "fecha_fin": fecha_fin,
            "estado": estado,
            "responsable_id": str(responsable) if responsable else "",
            "protocolo_archivo": archivo_nombre or ""
        }
        dvh = sum(len(str(v)) for v in datos.values() if v is not None)
        cur.execute("UPDATE experimentos SET dvh = ? WHERE id = ?", (dvh, nuevo_id))
        conn.commit()
        # Ejecutar tareas en segundo plano
        lanzar_tarea_en_segundo_plano(
            post_proceso_experimento,
            "CREAR EXPERIMENTO",
            nuevo_id,
            datos,
            request.remote_addr,
            session.get("usuario_id")
        )
        flash("Experimento agregado correctamente.", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Error al agregar el experimento: {str(e)}", "error")
    finally:
        conn.close()
    return redirect(url_for("experiments_bp.experiments"))
@experiments_bp.route("/get/<int:id>")
def get_experiment(id):
    """Obtiene los detalles de un experimento específico.
    Args:
        id (int): ID del experimento a consultar
    Returns:
        JSON: Datos del experimento o mensaje de error
    """
    if "usuario_id" not in session:
        return jsonify({"error": "No autenticado."}), 401
    conn = conectar_bd()
    try:
        cur = conn.cursor()
        # Consultar el experimento específico
        cur.execute("""
            SELECT 
                id, titulo, descripcion, 
                fecha_inicio, fecha_fin, 
                estado, protocolo_archivo, 
                responsable_id
            FROM experimentos
            WHERE id = ? 
            AND (estado_logico = 0 OR estado_logico IS NULL)
        """, (id,))
        row = cur.fetchone()
        if not row:
            return jsonify({"error": "Experimento no encontrado."}), 404
        # Verificar permisos
        if (session.get("rol") != "admin" and 
                row["responsable_id"] != session.get("usuario_id")):
            return jsonify({"error": "No autorizado."}), 403

        data = {"experimento": dict(row)}

        # Si es admin, incluir la lista de usuarios para permitir reasignar responsable
        if session.get("rol") == "admin":
            cur.execute("""
                SELECT id, nombre 
                FROM usuarios 
                WHERE estado_logico = 0 OR estado_logico IS NULL 
                ORDER BY nombre ASC
            """)
            usuarios = [dict(u) for u in cur.fetchall()]
            data["usuarios"] = usuarios

        return jsonify(data)
    except Exception as e:
        return jsonify({"error": f"Error al obtener el experimento: {str(e)}"}), 500
    finally:
        conn.close()
@experiments_bp.route("/update/<int:id>", methods=["POST"])
def update_experiment(id):
    """Actualiza un experimento existente.
    Args:
        id (int): ID del experimento a actualizar
    Returns:
        Response: Redirección al listado de experimentos
    """
    from servidor import lanzar_tarea_en_segundo_plano
    if "usuario_id" not in session:
        flash("Debes iniciar sesión para realizar esta acción.", "error")
        return redirect(url_for("login_bp.login"))
    conn = conectar_bd()
    try:
        cur = conn.cursor()
        # Verificar que el experimento existe y el usuario tiene permisos
        cur.execute("""
            SELECT responsable_id, protocolo_archivo 
            FROM experimentos 
            WHERE id = ?
        """, (id,))
        experimento = cur.fetchone()
        if not experimento:
            flash("Experimento no encontrado.", "error")
            return redirect(url_for("experiments_bp.experiments"))
        # Verificar permisos
        if (session.get("rol") != "admin" and 
                experimento["responsable_id"] != session.get("usuario_id")):
            flash("No tienes permiso para editar este experimento.", "error")
            return redirect(url_for("experiments_bp.experiments"))
        # Obtener datos del formulario
        titulo = request.form.get("titulo")
        descripcion = request.form.get("descripcion")
        fecha_inicio = request.form.get("fecha_inicio")
        fecha_fin = request.form.get("fecha_fin")
        estado = request.form.get("estado")
        # Validar que la fecha de inicio no sea anterior a la actual
        if fecha_inicio:
            from datetime import datetime
            try:
                fecha_inicio_dt = datetime.strptime(fecha_inicio, "%Y-%m-%d").date()
                if fecha_inicio_dt < datetime.now().date():
                    flash("No puedes hacer reservas en fechas pasadas.", "error")
                    return redirect(url_for("experiments_bp.experiments"))
            except ValueError:
                flash("Formato de fecha inválido.", "error")
                return redirect(url_for("experiments_bp.experiments"))
        # Determinar el responsable del experimento
        if session.get("rol") == "admin":
            responsable = request.form.get("responsable") or experimento["responsable_id"]
        else:
            responsable = experimento["responsable_id"]
        # Manejo de archivo de protocolo
        archivo = request.files.get("protocolo")
        archivo_nombre = experimento["protocolo_archivo"]  # Mantener el archivo actual por defecto
        if archivo and archivo.filename:
            try:
                # Si hay un archivo nuevo, guardarlo
                archivo_nombre = secure_filename(archivo.filename)
                archivo.save(os.path.join(UPLOAD_FOLDER, archivo_nombre))
            except Exception as e:
                flash(f"Error al guardar el archivo: {str(e)}", "error")
                return redirect(url_for("experiments_bp.experiments"))
        # Actualizar el experimento
        cur.execute("""
            UPDATE experimentos 
            SET titulo = ?, descripcion = ?, fecha_inicio = ?, 
                fecha_fin = ?, estado = ?, responsable_id = ?, protocolo_archivo = ?
            WHERE id = ?
        """, (
            titulo, descripcion, fecha_inicio, 
            fecha_fin, estado, responsable, archivo_nombre, id
        ))
        # Calcular y actualizar DVH
        datos = {
            "titulo": titulo,
            "descripcion": descripcion,
            "fecha_inicio": fecha_inicio,
            "fecha_fin": fecha_fin,
            "estado": estado,
            "responsable_id": str(responsable) if responsable else "",
            "protocolo_archivo": archivo_nombre or ""
        }
        dvh = sum(len(str(v)) for v in datos.values())
        cur.execute("UPDATE experimentos SET dvh = ? WHERE id = ?", (dvh, id))
        conn.commit()
        # Ejecutar tareas en segundo plano
        lanzar_tarea_en_segundo_plano(
            post_proceso_experimento,
            "ACTUALIZAR EXPERIMENTO",
            id,
            datos,
            request.remote_addr,
            session.get("usuario_id")
        )
        flash("Experimento actualizado correctamente.", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Error al actualizar el experimento: {str(e)}", "error")
    finally:
        conn.close()
    return redirect(url_for("experiments_bp.experiments"))
@experiments_bp.route("/delete/<int:id>", methods=["POST"])
def delete_experiment(id):
    """Elimina lógicamente un experimento del sistema.
    Args:
        id (int): ID del experimento a eliminar
    Returns:
        Response: Redirección al listado de experimentos
    """
    from servidor import lanzar_tarea_en_segundo_plano
    if "usuario_id" not in session or session.get("rol") != "admin":
        flash("No tienes permisos para realizar esta acción.", "error")
        return redirect(url_for("login_bp.login"))
    conn = conectar_bd()
    try:
        cur = conn.cursor()
        # Obtener datos del experimento antes de eliminarlo
        cur.execute("SELECT * FROM experimentos WHERE id = ?", (id,))
        experimento = cur.fetchone()
        if not experimento:
            flash("Experimento no encontrado.", "error")
            return redirect(url_for("experiments_bp.experiments"))
        # Eliminar lógicamente el experimento (marcar como eliminado)
        cur.execute(
            "UPDATE experimentos SET estado_logico = 1 WHERE id = ?", 
            (id,)
        )
        conn.commit()
        # Ejecutar tareas en segundo plano
        lanzar_tarea_en_segundo_plano(
            post_proceso_experimento,
            "ELIMINAR EXPERIMENTO",
            id,
            dict(experimento),
            request.remote_addr,
            session.get("usuario_id")
        )
        flash("Experimento eliminado correctamente.", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Error al eliminar el experimento: {str(e)}", "error")
    finally:
        conn.close()
    return redirect(url_for("experiments_bp.experiments"))
@experiments_bp.route("/protocolo/<filename>")
def descargar_protocolo(filename):
    """Permite la descarga de un archivo de protocolo.
    Args:
        filename (str): Nombre del archivo a descargar
    Returns:
        Response: Archivo para descargar
    """
    if "usuario_id" not in session:
        flash("Debes iniciar sesión para descargar archivos.", "error")
        return redirect(url_for("login_bp.login"))
    try:
        return send_from_directory(
            UPLOAD_FOLDER, 
            filename, 
            as_attachment=True
        )
    except Exception as e:
        flash(f"Error al descargar el archivo: {str(e)}", "error")
        return redirect(url_for("experiments_bp.experiments"))
@experiments_bp.route("/events")
def experiments_events():
    """Devuelve los experimentos como eventos para FullCalendar."""
    if "usuario_id" not in session:
        return jsonify([])

    conn = conectar_bd()
    try:
        cur = conn.cursor()
        rol = session.get("rol")
        usuario_id = session.get("usuario_id")

        if rol == "admin":
            cur.execute("""
                SELECT e.id, e.titulo, e.fecha_inicio, e.fecha_fin, e.estado,
                       u.nombre AS responsable, e.responsable_id
                FROM experimentos e
                LEFT JOIN usuarios u ON e.responsable_id = u.id
                WHERE e.estado_logico = 0 OR e.estado_logico IS NULL
            """)
            filas = cur.fetchall()
        else:
            cur.execute("""
                SELECT e.id, e.titulo, e.fecha_inicio, e.fecha_fin, e.estado,
                       u.nombre AS responsable, e.responsable_id
                FROM experimentos e
                LEFT JOIN usuarios u ON e.responsable_id = u.id
                WHERE (e.estado_logico = 0 OR e.estado_logico IS NULL)
                  AND e.responsable_id = ?
            """, (usuario_id,))
            filas = cur.fetchall()

        eventos = []
        for e in filas:
            # Color diferente si el responsable es el usuario actual
            color = "#1a237e" if e["responsable_id"] == usuario_id else "#90a4ae"
            eventos.append({
                "id": e["id"],
                "title": f"{e['titulo']} ({e['responsable'] or 'Sin responsable'})",
                "start": e["fecha_inicio"],
                "end": e["fecha_fin"],
                "color": color,
                "textColor": "#fff",
            })

        return jsonify(eventos)
    except Exception as e:
        print(f"Error obteniendo eventos de experimentos: {e}")
        return jsonify([])
    finally:
        conn.close()