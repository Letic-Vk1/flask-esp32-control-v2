import os
import time # 💡 Importar para usar marcas de tiempo (timestamp)
from flask import Flask, jsonify
import redis

# --- 1. CONFIGURACIÓN DE REDIS ---
REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
r = redis.from_url(REDIS_URL, decode_responses=True)

# Claves de los LEDs en Redis
LED_KEY_PREFIX = "led:"
LED1_KEY = LED_KEY_PREFIX + "1"
LED2_KEY = LED_KEY_PREFIX + "2"
LAST_HEARTBEAT_KEY = "esp:heartbeat" # 💡 Nueva clave para el latido

# 💡 TIEMPO LÍMITE: Si no recibimos un latido en 15s, asumimos desconexión
HEARTBEAT_TIMEOUT_SECONDS = 15 

# --- 2. INICIALIZACIÓN Y CONFIGURACIÓN ---
app = Flask(__name__)

# Inicializar el estado de los LEDs en Redis si no existen.
if not r.exists(LED1_KEY):
    r.set(LED1_KEY, 'False')
if not r.exists(LED2_KEY):
    r.set(LED2_KEY, 'False')
if not r.exists(LAST_HEARTBEAT_KEY):
    r.set(LAST_HEARTBEAT_KEY, 0) # Inicializar el timestamp

# --- 3. FUNCIONES AUXILIARES ---

def get_led_status():
    """Obtiene el estado actual (deseado) de ambos LEDs desde Redis."""
    status_values = r.mget([LED1_KEY, LED2_KEY])
    
    # Convierte las cadenas ('True'/'False') de Redis a booleanos de Python
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
    return "Servidor Flask para Control de LEDs con Persistencia Redis y Heartbeat - OK"

# 💡 RUTA DE HEARTBEAT (EL ESP32 LLAMA AQUÍ CADA 10 SEGUNDOS)
@app.route("/heartbeat", methods=["POST"])
def heartbeat():
    """Ruta para que el ESP32 reporte que está vivo."""
    # Guarda la marca de tiempo actual (timestamp en segundos) en Redis
    r.set(LAST_HEARTBEAT_KEY, int(time.time()))
    return jsonify({"message": "Heartbeat OK"}), 200


@app.route("/led/status")
def get_status():
    """Ruta GET para que el ESP32 y la App móvil consulten el estado y la conexión."""
    
    status = get_led_status() # Estado deseado de LEDs
    
    # --- Lógica de Verificación de Heartbeat ---
    last_heartbeat_str = r.get(LAST_HEARTBEAT_KEY)
    is_online = False
    
    if last_heartbeat_str and last_heartbeat_str != '0':
        try:
            # Convierte el string del timestamp de Redis a entero
            last_heartbeat = int(last_heartbeat_str)
            
            # Calcula la diferencia de tiempo
            time_since_last_beat = time.time() - last_heartbeat
            
            # Si el último latido fue hace menos de 15 segundos, está en línea.
            if time_since_last_beat < HEARTBEAT_TIMEOUT_SECONDS:
                is_online = True
            
        except ValueError:
            # Si hay un error al convertir el timestamp, asumimos desconexión por seguridad
            is_online = False 
    
    # 💡 Añadir el estado de conexión a la respuesta
    status['online'] = is_online
    
    # Retorna: {"led1": true, "led2": false, "online": true/false}
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
