import os
import json
import time
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, abort
from redis import Redis
import logging

# --- Configuración Inicial ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Usa REDIS_URL de las variables de entorno para la conexión
REDIS_URL = os.environ.get('REDIS_URL')

app = Flask(__name__)

# Intentar conectar a Redis.
try:
    r = None
    if REDIS_URL:
        # Configuración para Redis en Render/Cloud
        import urllib.parse as urlparse
        url = urlparse.urlparse(REDIS_URL)

        r = Redis(
            host=url.hostname,
            port=url.port,
            password=url.password,
            db=0,
            decode_responses=True # CRÍTICO: Para obtener strings/ints directamente
        )
        r.ping()
        logger.info("Conexión a Redis exitosa.")
    else:
        # Fallback a Redis local (solo para desarrollo)
        r = Redis(decode_responses=True)
        r.ping()
        logger.warning("Usando Redis local. Configura REDIS_URL para producción.")
except Exception as e:
    logger.error(f"Error al conectar con Redis: {e}")
    r = None 

# Claves de Redis para los estados y el heartbeat
LED1_STATE_KEY = "esp32:led1_state"
LED2_STATE_KEY = "esp32:led2_state"
HEARTBEAT_KEY = "esp32:last_heartbeat"
RESET_COMMAND_KEY = "esp32:reset_command" 
HEARTBEAT_TIMEOUT_SECONDS = 60 # Tiempo máximo para considerar el ESP32 online

# Inicializar los estados del LED y el comando de reseteo
if r:
    if r.get(LED1_STATE_KEY) is None:
        r.set(LED1_STATE_KEY, 0)
    if r.get(LED2_STATE_KEY) is None:
        r.set(LED2_STATE_KEY, 0)
    # Inicializar el comando de reseteo a 0 (Falso)
    if r.get(RESET_COMMAND_KEY) is None:
        r.set(RESET_COMMAND_KEY, 0)
    logger.info("Estados iniciales de LED1, LED2 y RESET establecidos.")


# --- Funciones de Utilidad ---

def _get_led_state(key):
    """Obtiene el estado del LED de Redis como entero (0 o 1)."""
    state = r.get(key)
    return int(state) if state is not None else 0

def _get_online_status():
    """Calcula si el ESP32 está online basado en el último heartbeat."""
    last_heartbeat_str = r.get(HEARTBEAT_KEY)
    if not last_heartbeat_str:
        return False
    
    try:
        last_time = datetime.fromisoformat(last_heartbeat_str)
        time_difference = datetime.now() - last_time
        return time_difference.total_seconds() < HEARTBEAT_TIMEOUT_SECONDS
    except ValueError:
        logger.warning("Formato de timestamp de Heartbeat inválido.")
        return False

# --- Rutas de la Aplicación ---

@app.before_request
def check_redis_status():
    """Verifica si Redis está disponible antes de procesar cualquier solicitud."""
    if r is None:
        return jsonify({"error": "Servicio de base de datos (Redis) no disponible."}), 503

# -----------------------------------------------------------
# RUTA 1: HEARTBEAT (USADA POR EL ESP32 PARA SINCRONIZAR)
# -----------------------------------------------------------
@app.route('/heartbeat', methods=['POST'])
def receive_heartbeat():
    """
    Ruta usada por el ESP32 para reportar actividad, solicitar el estado deseado
    de los LEDs y verificar si hay un comando de reseteo pendiente.
    """
    try:
        # 1. Actualizar el registro de actividad
        timestamp = datetime.now().isoformat()
        r.set(HEARTBEAT_KEY, timestamp)
        logger.info(f"Heartbeat recibido. Última actividad: {timestamp}")

        # 2. Devolver el estado deseado de los LEDs
        led1_state = _get_led_state(LED1_STATE_KEY)
        led2_state = _get_led_state(LED2_STATE_KEY)
        
        # 3. Leer y preparar el comando de reseteo (si es 1, el ESP32 debe resetearse)
        reset_command = r.get(RESET_COMMAND_KEY)
        
        # Si el ESP32 lee el comando de reseteo (1), lo borra (lo pone a 0) 
        # en la base de datos para no repetirlo innecesariamente.
        if reset_command == '1':
             r.set(RESET_COMMAND_KEY, 0) # Borrar la bandera después de enviarla
             logger.warning("Bandera de RESET enviada al ESP32 y borrada de Redis.")


        # 4. El ESP32 espera un JSON con los estados y el comando de reset
        return jsonify({
            "led1": led1_state,
            "led2": led2_state,
            "reset_wifi": reset_command == '1' # Envía True si el valor era 1
        })

    except Exception as e:
        logger.error(f"Error en el heartbeat: {e}")
        return jsonify({"error": "Error interno del servidor", "details": str(e)}), 500

# -----------------------------------------------------------
# RUTA 2: LED STATUS (USADA POR LA APP FLUTTER PARA POLLING)
# -----------------------------------------------------------
@app.route('/led/status', methods=['GET'])
def get_led_status():
    """
    Ruta usada por la aplicación Flutter para obtener el estado deseado
    de los LEDs y si el ESP32 está online.
    """
    try:
        led1_state = _get_led_state(LED1_STATE_KEY)
        led2_state = _get_led_state(LED2_STATE_KEY)
        is_online = _get_online_status()

        # Flutter espera booleanos (True/False)
        return jsonify({
            "led1": led1_state == 1,
            "led2": led2_state == 1,
            "online": is_online
        })
    except Exception as e:
        logger.error(f"Error al obtener el estado del sistema: {e}")
        return jsonify({"error": "Error interno al obtener el estado"}), 500

# -----------------------------------------------------------
# RUTA 3: CONTROL DE LEDS (USADA POR LA APP FLUTTER)
# -----------------------------------------------------------
@app.route('/led/<action>/<int:numero>', methods=['POST'])
def control_led(action, numero):
    """
    Ruta para cambiar el estado de un LED específico.
    """
    if numero not in [1, 2]:
        abort(400, description="Número de LED inválido. Solo se acepta 1 o 2.")
    
    if action not in ['on', 'off']:
        abort(400, description="Acción inválida. Solo se acepta 'on' u 'off'.")
    
    # Determinar el nuevo estado y la clave de Redis
    new_state = 1 if action == 'on' else 0
    key_to_set = LED1_STATE_KEY if numero == 1 else LED2_STATE_KEY
    
    try:
        # Guardar el nuevo estado en Redis
        r.set(key_to_set, new_state)
        logger.info(f"Estado del LED {numero} cambiado a: {action.upper()}")
        
        # Respuesta exitosa para Flutter
        return jsonify({"success": True, "led": numero, "new_state": new_state})
    except Exception as e:
        logger.error(f"Error al controlar el LED: {e}")
        return jsonify({"error": "Error al actualizar Redis."}), 500

# -----------------------------------------------------------
# RUTA 4: BORRADO DE CREDENCIALES (NUEVA RUTA DESDE FLUTTER)
# -----------------------------------------------------------
@app.route('/credentials/reset', methods=['POST'])
def reset_credentials():
    """
    Establece la bandera en Redis para que el ESP32 borre sus credenciales.
    """
    try:
        # Poner la bandera de reseteo en 1 (Verdadero)
        r.set(RESET_COMMAND_KEY, 1)
        logger.warning("Comando de reseteo de credenciales guardado en Redis (bandera = 1).")
        return jsonify({
            "success": True, 
            "message": "Comando de reseteo enviado. El ESP32 lo ejecutará en el próximo heartbeat."
        })
    except Exception as e:
        logger.error(f"Error al guardar el comando de reseteo: {e}")
        return jsonify({"error": "Error al comunicar con Redis para el reseteo."}), 500


if __name__ == '__main__':
    # Usar el puerto 5000 para desarrollo local
    app.run(host='0.0.0.0', port=5000, debug=True)
