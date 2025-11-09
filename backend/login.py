import os
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from datetime import datetime
import bcrypt
from db import ejecutar_select, ejecutar_insert, ejecutar_update, registrar_auditoria, recalcular_dvv

# Ruta absoluta al frontend/pages/login
template_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend", "pages", "login")

login_bp = Blueprint("login_bp", __name__, template_folder=template_dir, static_folder=template_dir)


# ===============================
# LOGIN
# ===============================
@login_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip()
        contraseña = request.form["contraseña"].strip()

        query = "SELECT * FROM usuarios WHERE email = ? AND estado_logico = 0"
        usuarios = ejecutar_select(query, (email,))

        if not usuarios:
            flash("Usuario no encontrado o eliminado.", "error")
            return render_template("login.html")

        usuario = usuarios[0]

        if bcrypt.checkpw(contraseña.encode("utf-8"), usuario["contraseña_hash"].encode("utf-8")):
            session["usuario_id"] = usuario["id"]
            session["nombre"] = usuario["nombre"]
            session["rol"] = usuario["rol"]

            ejecutar_update("UPDATE usuarios SET ultima_sesion = ? WHERE id = ?", (datetime.now(), usuario["id"]))
            registrar_auditoria(usuario["id"], "LOGIN EXITOSO", "usuarios", usuario["id"], request.remote_addr)
            recalcular_dvv("usuarios")

            flash(f"Bienvenido {usuario['nombre']} 👋", "success")
            return redirect(url_for("home"))
        else:
            registrar_auditoria(None, "LOGIN FALLIDO", "usuarios", 0, request.remote_addr)
            flash("Contraseña incorrecta.", "error")

    return render_template("login.html")


# ===============================
# REGISTRO
# ===============================
@login_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        nombre = request.form["nombre"].strip()
        email = request.form["email"].strip()
        contraseña = request.form["contraseña"].strip()
        rol = "usuario"

        # Verificar si ya existe el correo
        existe = ejecutar_select("SELECT * FROM usuarios WHERE email = ?", (email,))
        if existe:
            flash("Este email ya está registrado.", "error")
            return render_template("register.html")

        # Crear hash seguro de la contraseña
        hash_contraseña = bcrypt.hashpw(contraseña.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

        # Insertar nuevo usuario
        query = """INSERT INTO usuarios (nombre, email, contraseña_hash, rol, estado_logico)
                   VALUES (?, ?, ?, ?, 0)"""
        nuevo_id = ejecutar_insert(query, (nombre, email, hash_contraseña, rol))

        # Auditoría
        registrar_auditoria(nuevo_id, "USUARIO REGISTRADO", "usuarios", nuevo_id, request.remote_addr)
        recalcular_dvv("usuarios")

        flash("Registro exitoso 🎉 Ya podés iniciar sesión.", "success")
        return redirect(url_for("login_bp.login"))

    return render_template("register.html")


# ===============================
# LOGOUT
# ===============================
@login_bp.route("/logout")
def logout():
    if "usuario_id" in session:
        usuario_id = session["usuario_id"]
        registrar_auditoria(usuario_id, "LOGOUT", "usuarios", usuario_id, request.remote_addr)
        session.clear()
        flash("Sesión cerrada correctamente.", "success")
    return redirect(url_for("login_bp.login"))
