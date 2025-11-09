import sqlite3
from sqlite3 import Error
import os
from datetime import datetime
import hashlib

# Ruta absoluta hacia la base en la raíz del proyecto
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "biolabhub.db")

def conectar_bd():
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn
    except Error as e:
        print("❌ Error al conectar con la base de datos:", e)


def crear_bd():
    conn = conectar_bd()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            contraseña_hash TEXT NOT NULL,
            rol TEXT NOT NULL,
            estado_logico INTEGER DEFAULT 0,
            dvh INTEGER,
            fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ultima_sesion TIMESTAMP
        )
        """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audits_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER,
            accion TEXT,
            tabla_afectada TEXT,
            registro_id INTEGER,
            fecha TIMESTAMP,
            ip_origen TEXT,
            dvh INTEGER,
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
        )
        """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS muestras (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            tipo TEXT,
            estado TEXT,
            responsable_id INTEGER,
            ubicacion TEXT,
            fecha_ingreso TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            estado_logico INTEGER DEFAULT 0,
            dvh INTEGER,
            FOREIGN KEY (responsable_id) REFERENCES usuarios(id)
        )
        """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reactivos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            stock INTEGER,
            fecha_caducidad DATE,
            proovedor TEXT,
            responsable_id INTEGER,
            estado_logico INTEGER DEFAULT 0,
            dvh INTEGER,
            FOREIGN KEY (responsable_id) REFERENCES usuarios(id)
        )
        """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS experimentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo TEXT NOT NULL,
            descripcion TEXT NOT NULL,
            responsable_id INTEGER,
            fecha_inicio DATE,
            fecha_fin DATE,
            estado TEXT,
            estado_logico INTEGER DEFAULT 0,
            dvh INTEGER,
            FOREIGN KEY (responsable_id) REFERENCES usuarios(id)
        )
        """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS verificaciones_verticales (
            tabla TEXT PRIMARY KEY,
            dvv INTEGER
        )
        """)
    
    conn.commit()
    print("base de datos creada correctamente")
    conn.close()

def calcular_dvh(datos):
    total = 0
    for valor in datos.values():
        total += len(str(valor))
    return total

def recalcular_dvv(tabla):
    conexion = conectar_bd()
    cursor = conexion.cursor()
    cursor.execute(f"SELECT dvh FROM {tabla} WHERE dvh IS NOT NULL")
    suma = sum(fila[0] for fila in cursor.fetchall())
    cursor.execute("SELECT dvv FROM verificaciones_verticales WHERE tabla=?", (tabla,))
    if cursor.fetchone():
        cursor.execute("UPDATE verificaciones_verticales SET dvv=? WHERE tabla=?", (suma, tabla))
    else:
        cursor.execute("INSERT INTO verificaciones_verticales (tabla, dvv) VALUES (?, ?)", (tabla, suma))
    conexion.commit()
    conexion.close()

def ejecutar_select(query, parametros=()):
    conn = conectar_bd()
    cursor = conn.cursor()
    cursor.execute(query, parametros)
    filas = cursor.fetchall()
    conn.close()
    return filas


def ejecutar_insert(query, parametros=()):
    conn = conectar_bd()
    cursor = conn.cursor()
    cursor.execute(query, parametros)
    conn.commit()
    last_id = cursor.lastrowid
    conn.close()
    return last_id


def ejecutar_update(query, parametros=()):
    conn = conectar_bd()
    cursor = conn.cursor()
    cursor.execute(query, parametros)
    conn.commit()
    conn.close()

def registrar_auditoria(usuario_id, accion, tabla, registro_id, ip_origen):
    datos = {
        "usuario_id": usuario_id,
        "accion": accion,
        "tabla_afectada": tabla,
        "registro_id": registro_id,
        "fecha": datetime.now(),
        "ip_origen": ip_origen
    }
    dvh = calcular_dvh(datos)

    query = """INSERT INTO audits_logs 
               (usuario_id, accion, tabla_afectada, registro_id, fecha, ip_origen, dvh)
               VALUES (?, ?, ?, ?, ?, ?, ?)"""

    ejecutar_insert(query, (usuario_id, accion, tabla, registro_id, datetime.now(), ip_origen, dvh))
    recalcular_dvv("audits_logs")


