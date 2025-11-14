import os
from flask import Flask, jsonify
import redis

# --- 1. CONFIGURACIÓN DE REDIS ---
# Lee la URL del entorno de Render (donde configuraste REDIS_URL), 
# o usa localhost:6379 como fallback para desarrollo local.
REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
r = redis.from_url(REDIS_URL, decode_responses=True)

# Claves de los LEDs en Redis
LED_KEY_PREFIX = "led:"
LED1_KEY = LED_KEY_PREFIX + "1"
LED2_KEY = LED_KEY_PREFIX + "2"

# --- 2. INICIALIZACIÓN Y CONFIGURACIÓN ---
app = Flask(__name__)

# Inicializar el estado de los LEDs en Redis si no existen.
# Esto asegura que siempre haya un valor booleano ('True' o 'False')
# para que el ESP32 pueda consultarlo.
if not r.exists(LED1_KEY):
    r.set(LED1_KEY, 'False')
if not r.exists(LED2_KEY):
    r.set(LED2_KEY, 'False')

# --- 3. FUNCIONES AUXILIARES ---

def get_led_status():
    """Obtiene el estado actual de ambos LEDs desde Redis."""
    # Usamos mget para obtener ambos valores eficientemente
    status_values = r.mget([LED1_KEY, LED2_KEY])
    
    # Convierte las cadenas ('True'/'False') de Redis a booleanos de Python
    return {
        "led1": status_values[0] == 'True',
        "led2": status_values[1] == 'True'
    }

def set_led_state(led_key, state):
    """Establece el estado de un LED en Redis."""
    # Guarda el booleano como cadena ('True' o 'False') en Redis
    r.set(led_key, 'True' if state else 'False')
    
# --- 4. RUTAS DE LA APLICACIÓN ---

@app.route("/")
def index():
    return "Servidor Flask para Control de LEDs con Persistencia Redis - Estado OK"

@app.route("/led/status")
def get_status():
    """Ruta GET para que el ESP32 y la App móvil consulten el estado actual."""
    status = get_led_status()
    # Retorna el estado JSON: {"led1": true, "led2": false}
    return jsonify(status), 200

@app.route("/led/on/<led>", methods=["GET", "POST"])
def led_on(led):
    """Ruta para encender un LED."""
    key = LED_KEY_PREFIX + led
    if r.exists(key):
        set_led_state(key, True)
        return jsonify({"message": f"LED {led} encendido"}), 200
    else:
        return jsonify({"error": "LED no encontrado"}), 404

@app.route("/led/off/<led>", methods=["GET", "POST"])
def led_off(led):
    """Ruta para apagar un LED."""
    key = LED_KEY_PREFIX + led
    if r.exists(key):
        set_led_state(key, False)
        return jsonify({"message": f"LED {led} apagado"}), 200
    else:
        return jsonify({"error": "LED no encontrado"}), 404

if __name__ == "__main__":
    app.run(debug=True)
