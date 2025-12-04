import os
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from datetime import datetime
import bcrypt
from db import ejecutar_select, ejecutar_insert, ejecutar_update, registrar_auditoria, recalcular_dvv

template_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend", "pages", "login")
login_bp = Blueprint("login_bp", __name__, template_folder=template_dir, static_folder=template_dir)

@login_bp.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":
        email = request.form["email"].strip()
        contraseña = request.form["contraseña"].strip()
        query = "SELECT * FROM usuarios WHERE email = ? AND estado_logico = 0"
        usuarios = ejecutar_select(query, (email,))
        if not usuarios:
            registrar_auditoria(None, "LOGIN FALLIDO", "usuarios", 0, request.remote_addr)

            from servidor import lanzar_tarea_en_segundo_plano

            def manejar_login_fallido_critico(ip_origen: str):
                try:
                    registros = ejecutar_select(
                        """
                        SELECT COUNT(*) AS cantidad
                        FROM audits_logs
                        WHERE accion = ?
                          AND ip_origen = ?
                        """,
                        ("LOGIN FALLIDO", ip_origen),
                    )
                    cantidad = registros[0]["cantidad"] if registros else 0
                    if cantidad >= 3:
                        try:
                            from servidor import socketio

                            registrar_auditoria(
                                None,
                                "ALERTA: MULTIPLES LOGINS FALLIDOS",
                                "usuarios",
                                0,
                                ip_origen,
                            )
                            socketio.emit(
                                "critical_event",
                                {
                                    "tipo": "LOGIN_FALLIDO_MULTIPLE",
                                    "ip": ip_origen,
                                    "cantidad": cantidad,
                                },
                            )
                        except Exception:
                            pass
                except Exception:
                    pass

            lanzar_tarea_en_segundo_plano(manejar_login_fallido_critico, request.remote_addr)

            flash("Usuario no encontrado o eliminado.", "error")
            return render_template("login.html")

        usuario = usuarios[0]
        hash_bd = usuario["contraseña_hash"]
        if bcrypt.checkpw(contraseña.encode("utf-8"), hash_bd.encode("utf-8")):
            session["usuario_id"] = usuario["id"]
            session["nombre"] = usuario["nombre"]
            session["rol"] = usuario["rol"]
            ejecutar_update(
                "UPDATE usuarios SET ultima_sesion = ? WHERE id = ?",
                (datetime.now(), usuario["id"])
            )
            registrar_auditoria(usuario["id"], "LOGIN EXITOSO", "usuarios", usuario["id"], request.remote_addr)
            recalcular_dvv("usuarios")
            flash(f"Bienvenido {usuario['nombre']} ", "success")
            return redirect(url_for("home_bp.home"))
        else:
            registrar_auditoria(None, "LOGIN FALLIDO", "usuarios", 0, request.remote_addr)

            from servidor import lanzar_tarea_en_segundo_plano

            def manejar_login_fallido_critico(ip_origen: str):
                try:
                    registros = ejecutar_select(
                        """
                        SELECT COUNT(*) AS cantidad
                        FROM audits_logs
                        WHERE accion = ?
                          AND ip_origen = ?
                        """,
                        ("LOGIN FALLIDO", ip_origen),
                    )
                    cantidad = registros[0]["cantidad"] if registros else 0
                    if cantidad >= 3:
                        try:
                            from servidor import socketio

                            registrar_auditoria(
                                None,
                                "ALERTA: MULTIPLES LOGINS FALLIDOS",
                                "usuarios",
                                0,
                                ip_origen,
                            )
                            socketio.emit(
                                "critical_event",
                                {
                                    "tipo": "LOGIN_FALLIDO_MULTIPLE",
                                    "ip": ip_origen,
                                    "cantidad": cantidad,
                                },
                            )
                        except Exception:
                            pass
                except Exception:
                    pass

            lanzar_tarea_en_segundo_plano(manejar_login_fallido_critico, request.remote_addr)
            flash("Contraseña incorrecta.", "error")

    return render_template("login.html")

@login_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        nombre = request.form["nombre"].strip()
        email = request.form["email"].strip()
        contraseña = request.form["contraseña"].strip()
        rol = "usuario"
        existe = ejecutar_select("SELECT * FROM usuarios WHERE email = ?", (email,))
        if existe:
            flash("Este email ya está registrado.", "error")
            return render_template("register.html")
        contraseña_hash = bcrypt.hashpw(
            contraseña.encode("utf-8"),
            bcrypt.gensalt()
        ).decode("utf-8")
        query = """
            INSERT INTO usuarios (nombre, email, contraseña_hash, rol, estado_logico)
            VALUES (?, ?, ?, ?, 0)
        """
        nuevo_id = ejecutar_insert(query, (nombre, email, contraseña_hash, rol))
        registrar_auditoria(nuevo_id, "USUARIO REGISTRADO", "usuarios", nuevo_id, request.remote_addr)
        recalcular_dvv("usuarios")
        flash("Registro exitoso  Ya podés iniciar sesión.", "success")
        return redirect(url_for("login_bp.login"))
    return render_template("register.html")
@login_bp.route("/logout")
def logout():
    if "usuario_id" in session:
        usuario_id = session["usuario_id"]
        registrar_auditoria(usuario_id, "LOGOUT", "usuarios", usuario_id, request.remote_addr)
        session.clear()
        flash("Sesión cerrada correctamente.", "success")
    return redirect(url_for("login_bp.login"))