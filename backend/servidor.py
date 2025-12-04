from flask import Flask, render_template, redirect, url_for, session, flash
import os
from db import crear_bd
from login import login_bp
from experiments import experiments_bp
from samples import samples_bp
from equipments import equipments_bp
from admin import admin_bp
from home import home_bp
from flask_socketio import SocketIO, emit
from threading import Thread
import time   

app = Flask(
    __name__,
    template_folder="../frontend/pages",
    static_folder="../frontend/static"
)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "clave_super_segura_para_biolabhub")
socketio = SocketIO(app, cors_allowed_origins="*")
def lanzar_tarea_en_segundo_plano(func, *args, **kwargs):
    hilo = Thread(target=func, args=args, kwargs=kwargs, daemon=True)
    hilo.start()
    return hilo
app.register_blueprint(home_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(login_bp)
app.register_blueprint(experiments_bp)
app.register_blueprint(samples_bp)
app.register_blueprint(equipments_bp)
@app.route("/")
def index():
    if "usuario_id" in session:
        return redirect(url_for("home_bp.home"))
    return render_template("landingpage/landingpage.html")

@app.route("/guest")
def guest():
    session.clear()
    session["rol"] = "invitado"
    return redirect(url_for("home_bp.home"))

@app.route("/equipment")
def equipment():
    if "usuario_id" not in session:
        flash("Debes iniciar sesión primero.", "error")
        return redirect(url_for("login_bp.login"))
    return "<h2>Página de Equipos (en construcción)</h2>"
@app.route("/reagents")
def reagents():
    if "usuario_id" not in session:
        flash("Debes iniciar sesión primero.", "error")
        return redirect(url_for("login_bp.login"))
    return "<h2>Página de Reactivos (en construcción)</h2>"
@socketio.on("connect")
def handle_connect():
    print(" Cliente conectado vía WebSocket")
    emit("server_message", {"msg": "Conectado al WebSocket de BioLabHub!"})
@socketio.on("disconnect")
def handle_disconnect():
    print(" Cliente desconectado")

if __name__ == "__main__":
    if not os.path.exists(os.path.join(os.path.dirname(__file__), "..", "biolabhub.db")):
        print(" Base de datos no encontrada. Creándola...")
        crear_bd()
    else:
        print(" Base de datos encontrada.")
    socketio.run(app, debug=True)