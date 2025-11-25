from flask import Flask, render_template, redirect, url_for, session, flash
import os
from db import crear_bd
from login import login_bp
from experiments import experiments_bp
from samples import samples_bp
from equipments import equipments_bp
from admin import admin_bp  # <- importa tu blueprint


# 🧩 IMPORTANTE → importar SocketIO
from flask_socketio import SocketIO, emit

# Crear app Flask
app = Flask(__name__,
            template_folder="../frontend/pages",
            static_folder="../frontend/static")

app.secret_key = "clave_super_segura_para_biolabhub"  # Necesaria para sesiones y flashes

# Inicializar SocketIO con CORS habilitado
socketio = SocketIO(app, cors_allowed_origins="*")

# Registrar Blueprints
app.register_blueprint(admin_bp)
app.register_blueprint(login_bp)
app.register_blueprint(experiments_bp)
app.register_blueprint(samples_bp)
app.register_blueprint(equipments_bp)


# 🔧 Ruta raíz → redirige al login si no hay sesión
@app.route("/")
def index():
    if "usuario_id" in session:
        return redirect(url_for("home"))
    return redirect(url_for("login_bp.login"))


# 🏠 Página principal (Home)
@app.route("/home")
def home():
    if "usuario_id" not in session:
        flash("Debes iniciar sesión primero.", "error")
        return redirect(url_for("login_bp.login"))
    return render_template("home/Home.html")


# ⚙️ Rutas base de ejemplo para futuros módulos
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


# 📡 EVENTOS SOCKET.IO

@socketio.on("connect")
def handle_connect():
    print("🟢 Cliente conectado vía WebSocket")
    emit("server_message", {"msg": "Conectado al WebSocket de BioLabHub!"})


@socketio.on("disconnect")
def handle_disconnect():
    print("🔴 Cliente desconectado")


# 🚀 Inicio del servidor y creación automática de la base de datos
if __name__ == "__main__":
    if not os.path.exists(os.path.join(os.path.dirname(__file__), "..", "biolabhub.db")):
        print("🔧 Base de datos no encontrada. Creándola...")
        crear_bd()
    else:
        print("✅ Base de datos encontrada.")

    # Cambiamos app.run → socketio.run
    socketio.run(app, debug=True)
