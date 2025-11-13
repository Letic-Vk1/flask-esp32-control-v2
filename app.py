import os
import json
from flask import Flask, request, jsonify
import paho.mqtt.publish as publish
from functools import wraps

# =========================================================
#                   CONFIGURACIÓN DE ENTORNO
# =========================================================
# NOTA: Estos valores se leen de las variables de entorno de Render.
# Debes configurarlas en el panel de control de Render (Environment Variables).

# Clave de seguridad (API_KEY) - Se utiliza para autenticar las peticiones entrantes desde Flutter
API_KEY = os.environ.get("RENDER_API_KEY") 
if not API_KEY:
    print("FATAL: La variable de entorno RENDER_API_KEY no está configurada.")

# Configuración del Broker MQTT
MQTT_BROKER_HOST = os.environ.get("MQTT_BROKER_HOST", "tu.broker.mqtt.com")
MQTT_BROKER_PORT = int(os.environ.get("MQTT_BROKER_PORT", 1883))

# Tópico MQTT al que el servidor publicará los comandos (debe coincidir con el ESP32)
MQTT_TOPIC = "iot/command/led_control"

app = Flask(__name__)

# =========================================================
#                   DECORADOR DE AUTENTICACIÓN
# =========================================================

def require_api_key(f):
    """
    Decorador para proteger las rutas, asegurando que solo las peticiones
    con la API Key correcta en el header 'X-API-Key' sean procesadas.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 1. Comprobar si la API Key está disponible en el entorno de Render
        if not API_KEY:
            # En un entorno de producción, esto debería ser un error crítico
            app.logger.error("API_KEY no configurada. Denegando acceso.")
            return jsonify({"error": "Configuración de seguridad incompleta en el servidor."}), 500

        # 2. Leer la clave enviada en el header de la petición
        sent_key = request.headers.get('X-API-Key')
        
        # 3. Comparar la clave enviada con la clave del entorno
        if sent_key and sent_key == API_KEY:
            return f(*args, **kwargs)
        else:
            app.logger.warning(f"Intento de acceso denegado. Clave enviada: {sent_key}")
            return jsonify({"error": "Acceso denegado. Clave API inválida."}), 403

    return decorated_function

# =========================================================
#                   RUTAS DEL SERVIDOR
# =========================================================

@app.route("/")
def home():
    """Ruta de prueba simple."""
    return "Servidor Flask IoT operativo y listo para recibir comandos.", 200

@app.route("/command", methods=["POST"])
@require_api_key
def handle_command():
    """
    Recibe el comando JSON de Flutter y lo publica al Broker MQTT.
    El ESP32, que está suscrito, recibe el mensaje en tiempo real.
    """
    try:
        data = request.get_json()
        
        # Validación de la estructura de datos
        led_id = data.get("ledId")
        state = data.get("state") # "on" o "off"

        if led_id not in [1, 2] or state not in ["on", "off"]:
            return jsonify({"error": "Payload JSON inválido. Se espera {'ledId': 1 o 2, 'state': 'on' o 'off'}"}), 400

        # Crear el mensaje JSON para el ESP32 (usando claves cortas para ahorrar bytes)
        # {"id": 1, "st": "on"}
        mqtt_payload = json.dumps({
            "id": led_id,
            "st": state
        })
        
        # =========================================================
        #                     PUBLICACIÓN MQTT
        # =========================================================
        
        # NOTA: Usamos la API_KEY como contraseña para el Broker MQTT,
        # lo que debe coincidir con cómo el ESP32 está configurado.
        
        publish.single(
            topic=MQTT_TOPIC,
            payload=mqtt_payload,
            hostname=MQTT_BROKER_HOST,
            port=MQTT_BROKER_PORT,
            auth={'username': '', 'password': API_KEY}, # Usamos API_KEY como contraseña
            qos=1 # Calidad de Servicio 1 (al menos una vez)
        )

        app.logger.info(f"Comando publicado al tópico {MQTT_TOPIC}: {mqtt_payload}")
        
        return jsonify({
            "status": "success",
            "message": f"Comando {state} para LED {led_id} publicado vía MQTT."
        }), 200

    except Exception as e:
        app.logger.error(f"Error procesando el comando: {e}")
        return jsonify({"error": f"Error interno del servidor: {e}"}), 500

if __name__ == "__main__":
    # Importante: Gunicorn es usado por Render. Este bloque es para pruebas locales.
    app.run(host='0.0.0.0', port=os.environ.get('PORT', 5000), debug=True)
