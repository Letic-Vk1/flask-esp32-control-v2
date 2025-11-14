import os
import time
from flask import Flask, jsonify
import redis

# --- 1. CONFIGURACIÓN DE REDIS ---
# Lee la URL del entorno de Render o usa localhost:6379 como fallback
REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
r = redis.from_url(REDIS_URL, decode_responses=True)

# Claves de los LEDs y del Heartbeat
LED_KEY_PREFIX = "led:"
LED1_KEY = LED_KEY_PREFIX + "1"
LED2_KEY = LED_KEY_PREFIX + "2"
LAST_HEARTBEAT_KEY = "esp:heartbeat" 

# 💡 TIEMPO LÍMITE (Se mantiene por si volvemos a usar el Heartbeat)
HEARTBEAT_TIMEOUT_SECONDS = 15 

# --- 2. INICIALIZACIÓN Y CONFIGURACIÓN ---
app = Flask(__name__)

# Inicializar el estado de los LEDs y el Heartbeat en Redis si no existen.
if not r.exists(LED1_KEY):
    r.set(LED1_KEY, 'False')
if not r.exists(LED2_KEY):
    r.set(LED2_KEY, 'False')
# Mantenemos la inicialización de Heartbeat para que el ESP32 pueda seguir enviando latidos
if not r.exists(LAST_HEARTBEAT_KEY):
    r.set(LAST_HEARTBEAT_KEY, 0) 

# --- 3. FUNCIONES AUXILIARES ---

def get_led_status():
    """Obtiene el estado actual (deseado) de ambos LEDs desde Redis."""
    status_values = r.mget([LED1_KEY, LED2_KEY])
    return {
        "led1": status_values[0] == 'True',
        "led2": status_values[1] == 'True'
    }

def set_led_state(led_key, state):
    """Establece el estado de un LED en Redis."""
    r.set(led_key, 'True' if state else 'False')
    
# --- 4. RUTAS DE LA APLICACIÓN ---

@app.route("/")
def index():
    return "Servidor Flask con Persistencia Redis y Heartbeat (Logic OFF) - OK"

# RUTA DE HEARTBEAT (EL ESP32 LLAMA AQUÍ CADA 10 SEGUNDOS)
@app.route("/heartbeat", methods=["POST"])
def heartbeat():
    """Ruta para que el ESP32 reporte que está vivo (NO USADA EN /led/status AHORA)."""
    r.set(LAST_HEARTBEAT_KEY, int(time.time()))
    return jsonify({"message": "Heartbeat OK"}), 200


@app.route("/led/status")
def get_status():
    """
    Ruta GET para que el ESP32 y la App consulten el estado.
    !!! IMPORTANTE: TEMPORALMENTE NO CONTIENE LÓGICA DE HEARTBEAT.
    """
    
    status = get_led_status()
    
    # Retorna solo: {"led1": true, "led2": false}
    return jsonify(status), 200

# Rutas de control de LED (sin cambios)
@app.route("/led/on/<led>", methods=["GET", "POST"])
def led_on(led):
    key = LED_KEY_PREFIX + led
    if r.exists(key):
        set_led_state(key, True)
        return jsonify({"message": f"LED {led} encendido"}), 200
    else:
        return jsonify({"error": "LED no encontrado"}), 404

@app.route("/led/off/<led>", methods=["GET", "POST"])
def led_off(led):
    key = LED_KEY_PREFIX + led
    if r.exists(key):
        set_led_state(key, False)
        return jsonify({"message": f"LED {led} apagado"}), 200
    else:
        return jsonify({"error": "LED no encontrado"}), 404

if __name__ == "__main__":
    app.run(debug=True)
