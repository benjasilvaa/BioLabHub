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
# API REST JSON
# -----------------------------
@experiments_bp.route("/api", methods=["GET"])
def api_list_experiments():
    """Lista experimentos en formato JSON para el usuario actual o admin."""
    if "usuario_id" not in session:
        return jsonify({"error": "No autenticado"}), 401

    conn = conectar_bd()
    try:
        cur = conn.cursor()
        rol = session.get("rol")
        usuario_id = session.get("usuario_id")

        if rol == "admin":
            cur.execute(
                """
                SELECT id, titulo, descripcion, fecha_inicio, fecha_fin,
                       estado, responsable_id, protocolo_archivo
                FROM experimentos
                WHERE estado_logico = 0 OR estado_logico IS NULL
                ORDER BY id DESC
                """
            )
        else:
            cur.execute(
                """
                SELECT id, titulo, descripcion, fecha_inicio, fecha_fin,
                       estado, responsable_id, protocolo_archivo
                FROM experimentos
                WHERE (estado_logico = 0 OR estado_logico IS NULL)
                  AND responsable_id = ?
                ORDER BY id DESC
                """,
                (usuario_id,),
            )
        filas = [dict(r) for r in cur.fetchall()]
        return jsonify({"experimentos": filas})
    except Exception as e:
        return jsonify({"error": f"Error al listar experimentos: {e}"}), 500
    finally:
        conn.close()


@experiments_bp.route("/api", methods=["POST"])
def api_create_experiment():
    """Crea un experimento recibiendo JSON y devuelve el registro creado."""
    from servidor import lanzar_tarea_en_segundo_plano

    if "usuario_id" not in session:
        return jsonify({"error": "No autenticado"}), 401

    data = request.get_json(silent=True) or {}
    titulo = (data.get("titulo") or "").strip()
    descripcion = (data.get("descripcion") or "").strip()
    fecha_inicio = data.get("fecha_inicio") or None
    fecha_fin = data.get("fecha_fin") or None
    estado = data.get("estado") or "Planificado"

    if not titulo or not descripcion:
        return jsonify({"error": "Título y descripción son obligatorios"}), 400

    # Validar fechas (no en pasado y fin no anterior a inicio)
    if fecha_inicio:
        from datetime import datetime

        try:
            fecha_inicio_dt = datetime.strptime(fecha_inicio, "%Y-%m-%d").date()
            if fecha_inicio_dt < datetime.now().date():
                return (
                    jsonify({"error": "La fecha de inicio no puede estar en el pasado."}),
                    400,
                )
            if fecha_fin:
                fecha_fin_dt = datetime.strptime(fecha_fin, "%Y-%m-%d").date()
                if fecha_fin_dt < fecha_inicio_dt:
                    return (
                        jsonify(
                            {
                                "error": "La fecha de fin no puede ser anterior a la fecha de inicio.",
                            }
                        ),
                        400,
                    )
        except ValueError:
            return jsonify({"error": "Formato de fecha inválido"}), 400

    # Determinar responsable
    if session.get("rol") == "admin" and data.get("responsable"):
        responsable = data.get("responsable")
    else:
        responsable = session.get("usuario_id")

    conn = conectar_bd()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO experimentos
            (titulo, descripcion, fecha_inicio, fecha_fin, estado,
             responsable_id, protocolo_archivo, dvh)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (titulo, descripcion, fecha_inicio, fecha_fin, estado, responsable, None, 0),
        )
        nuevo_id = cur.lastrowid
        conn.commit()

        datos = {
            "titulo": titulo,
            "descripcion": descripcion,
            "fecha_inicio": fecha_inicio,
            "fecha_fin": fecha_fin,
            "estado": estado,
            "responsable_id": str(responsable) if responsable else "",
            "protocolo_archivo": "",
        }
        dvh = sum(len(str(v)) for v in datos.values() if v is not None)
        cur.execute("UPDATE experimentos SET dvh = ? WHERE id = ?", (dvh, nuevo_id))
        conn.commit()

        lanzar_tarea_en_segundo_plano(
            post_proceso_experimento,
            "CREAR EXPERIMENTO (API)",
            nuevo_id,
            datos,
            request.remote_addr,
            session.get("usuario_id"),
        )

        datos["id"] = nuevo_id
        return jsonify({"mensaje": "Experimento creado", "experimento": datos}), 201
    except Exception as e:
        conn.rollback()
        return jsonify({"error": f"Error al crear experimento: {e}"}), 500
    finally:
        conn.close()


@experiments_bp.route("/api/<int:id>", methods=["GET"])
def api_get_experiment(id):
    """Obtiene un experimento específico en formato JSON."""
    if "usuario_id" not in session:
        return jsonify({"error": "No autenticado"}), 401

    conn = conectar_bd()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, titulo, descripcion, fecha_inicio, fecha_fin,
                   estado, responsable_id, protocolo_archivo
            FROM experimentos
            WHERE id = ? AND (estado_logico = 0 OR estado_logico IS NULL)
            """,
            (id,),
        )
        row = cur.fetchone()
        if not row:
            return jsonify({"error": "Experimento no encontrado"}), 404

        if session.get("rol") != "admin" and row["responsable_id"] != session.get(
            "usuario_id"
        ):
            return jsonify({"error": "No autorizado"}), 403

        return jsonify({"experimento": dict(row)})
    except Exception as e:
        return jsonify({"error": f"Error al obtener experimento: {e}"}), 500
    finally:
        conn.close()


@experiments_bp.route("/api/<int:id>", methods=["PUT"])
def api_update_experiment(id):
    """Actualiza un experimento a partir de JSON."""
    from servidor import lanzar_tarea_en_segundo_plano

    if "usuario_id" not in session:
        return jsonify({"error": "No autenticado"}), 401

    data = request.get_json(silent=True) or {}

    conn = conectar_bd()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM experimentos WHERE id = ?", (id,))
        experimento = cur.fetchone()
        if not experimento:
            return jsonify({"error": "Experimento no encontrado"}), 404

        if session.get("rol") != "admin" and experimento["responsable_id"] != session.get(
            "usuario_id"
        ):
            return jsonify({"error": "No autorizado"}), 403

        titulo = (data.get("titulo") or experimento["titulo"]).strip()
        descripcion = (data.get("descripcion") or experimento["descripcion"]).strip()
        fecha_inicio = data.get("fecha_inicio") or experimento["fecha_inicio"]
        fecha_fin = data.get("fecha_fin") or experimento["fecha_fin"]
        estado = data.get("estado") or experimento["estado"]

        # Validar fechas
        if fecha_inicio:
            from datetime import datetime

            try:
                fecha_inicio_dt = datetime.strptime(fecha_inicio, "%Y-%m-%d").date()
                if fecha_inicio_dt < datetime.now().date():
                    return (
                        jsonify({"error": "La fecha de inicio no puede estar en el pasado."}),
                        400,
                    )
                if fecha_fin:
                    fecha_fin_dt = datetime.strptime(fecha_fin, "%Y-%m-%d").date()
                    if fecha_fin_dt < fecha_inicio_dt:
                        return (
                            jsonify(
                                {
                                    "error": "La fecha de fin no puede ser anterior a la fecha de inicio.",
                                }
                            ),
                            400,
                        )
            except ValueError:
                return jsonify({"error": "Formato de fecha inválido"}), 400

        if session.get("rol") == "admin" and data.get("responsable"):
            responsable = data.get("responsable")
        else:
            responsable = experimento["responsable_id"]

        cur.execute(
            """
            UPDATE experimentos
            SET titulo = ?, descripcion = ?, fecha_inicio = ?, fecha_fin = ?,
                estado = ?, responsable_id = ?
            WHERE id = ?
            """,
            (titulo, descripcion, fecha_inicio, fecha_fin, estado, responsable, id),
        )

        datos = {
            "titulo": titulo,
            "descripcion": descripcion,
            "fecha_inicio": fecha_inicio,
            "fecha_fin": fecha_fin,
            "estado": estado,
            "responsable_id": str(responsable) if responsable else "",
            "protocolo_archivo": experimento["protocolo_archivo"] or "",
        }
        dvh = sum(len(str(v)) for v in datos.values())
        cur.execute("UPDATE experimentos SET dvh = ? WHERE id = ?", (dvh, id))
        conn.commit()

        lanzar_tarea_en_segundo_plano(
            post_proceso_experimento,
            "ACTUALIZAR EXPERIMENTO (API)",
            id,
            datos,
            request.remote_addr,
            session.get("usuario_id"),
        )

        datos["id"] = id
        return jsonify({"mensaje": "Experimento actualizado", "experimento": datos})
    except Exception as e:
        conn.rollback()
        return jsonify({"error": f"Error al actualizar experimento: {e}"}), 500
    finally:
        conn.close()


@experiments_bp.route("/api/<int:id>", methods=["DELETE"])
def api_delete_experiment(id):
    """Elimina lógicamente un experimento desde la API JSON."""
    from servidor import lanzar_tarea_en_segundo_plano

    if "usuario_id" not in session:
        return jsonify({"error": "No autenticado"}), 401

    conn = conectar_bd()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM experimentos WHERE id = ?", (id,))
        experimento = cur.fetchone()
        if not experimento:
            return jsonify({"error": "Experimento no encontrado"}), 404

        responsable_id = experimento["responsable_id"]
        usuario_actual = session.get("usuario_id")
        es_admin = session.get("rol") == "admin"
        if not es_admin and usuario_actual != responsable_id:
            return jsonify({"error": "Solo el responsable o un administrador pueden eliminar este experimento."}), 403

        cur.execute(
            "UPDATE experimentos SET estado_logico = 1 WHERE id = ?",
            (id,),
        )
        conn.commit()

        lanzar_tarea_en_segundo_plano(
            post_proceso_experimento,
            "ELIMINAR EXPERIMENTO (API)",
            id,
            dict(experimento),
            request.remote_addr,
            session.get("usuario_id"),
        )

        return jsonify({"mensaje": "Experimento eliminado"})
    except Exception as e:
        conn.rollback()
        return jsonify({"error": f"Error al eliminar experimento: {e}"}), 500
    finally:
        conn.close()


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
    # Validar fechas (no en pasado y fin no anterior a inicio)
    if fecha_inicio:
        from datetime import datetime
        try:
            fecha_inicio_dt = datetime.strptime(fecha_inicio, "%Y-%m-%d").date()
            if fecha_inicio_dt < datetime.now().date():
                flash("La fecha de inicio no puede estar en el pasado.", "error")
                return redirect(url_for("experiments_bp.experiments"))
            if fecha_fin:
                fecha_fin_dt = datetime.strptime(fecha_fin, "%Y-%m-%d").date()
                if fecha_fin_dt < fecha_inicio_dt:
                    flash("La fecha de fin no puede ser anterior a la fecha de inicio.", "error")
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
        if (session.get("rol") != "admin" and 
                experimento["responsable_id"] != session.get("usuario_id")):
            flash("No tienes permiso para editar este experimento.", "error")
            return redirect(url_for("experiments_bp.experiments"))
        titulo = request.form.get("titulo")
        descripcion = request.form.get("descripcion")
        fecha_inicio = request.form.get("fecha_inicio")
        fecha_fin = request.form.get("fecha_fin")
        estado = request.form.get("estado")
        if fecha_inicio:
            from datetime import datetime
            try:
                fecha_inicio_dt = datetime.strptime(fecha_inicio, "%Y-%m-%d").date()
                if fecha_inicio_dt < datetime.now().date():
                    flash("La fecha de inicio no puede estar en el pasado.", "error")
                    return redirect(url_for("experiments_bp.experiments"))
                if fecha_fin:
                    fecha_fin_dt = datetime.strptime(fecha_fin, "%Y-%m-%d").date()
                    if fecha_fin_dt < fecha_inicio_dt:
                        flash("La fecha de fin no puede ser anterior a la fecha de inicio.", "error")
                        return redirect(url_for("experiments_bp.experiments"))
            except ValueError:
                flash("Formato de fecha inválido.", "error")
                return redirect(url_for("experiments_bp.experiments"))
        if session.get("rol") == "admin":
            responsable = request.form.get("responsable") or experimento["responsable_id"]
        else:
            responsable = experimento["responsable_id"]
        archivo = request.files.get("protocolo")
        archivo_nombre = experimento["protocolo_archivo"]
        if archivo and archivo.filename:
            try:
                archivo_nombre = secure_filename(archivo.filename)
                archivo.save(os.path.join(UPLOAD_FOLDER, archivo_nombre))
            except Exception as e:
                flash(f"Error al guardar el archivo: {str(e)}", "error")
                return redirect(url_for("experiments_bp.experiments"))
        cur.execute("""
            UPDATE experimentos 
            SET titulo = ?, descripcion = ?, fecha_inicio = ?, 
                fecha_fin = ?, estado = ?, responsable_id = ?, protocolo_archivo = ?
            WHERE id = ?
        """, (
            titulo, descripcion, fecha_inicio, 
            fecha_fin, estado, responsable, archivo_nombre, id
        ))
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
    if "usuario_id" not in session:
        flash("Debes iniciar sesión para realizar esta acción.", "error")
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

        responsable_id = experimento["responsable_id"]
        usuario_actual = session.get("usuario_id")
        es_admin = session.get("rol") == "admin"
        if not es_admin and usuario_actual != responsable_id:
            flash("Solo el responsable o un administrador pueden eliminar este experimento.", "error")
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