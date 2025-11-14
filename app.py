from flask import Flask, jsonify, request
from flask_cors import CORS
# Importamos la librería de Redis
import redis
import os, json

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# --- CONEXIÓN A REDIS ---
# Render usará la variable de entorno REDIS_URL para la conexión.
# Si no está definida (ej. desarrollo local), usamos una configuración local por defecto.
REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
r = redis.from_url(REDIS_URL, decode_responses=True)

# Clave donde guardaremos el estado de los LEDs en Redis
LED_KEY = "LED_STATUS"

# --- Inicialización del Estado en Redis ---
# Solo inicializa los valores si la clave LED_STATUS no existe
if not r.exists(LED_KEY):
    # Guardamos el JSON del estado inicial como una cadena en Redis
    estado_inicial = {"led1": False, "led2": False}
    r.set(LED_KEY, json.dumps(estado_inicial))
    print("✅ Estado inicial de LEDs configurado en Redis.")


def leer_leds():
    """Lee el estado de los LEDs desde Redis y lo convierte a un diccionario Python."""
    # Obtenemos la cadena JSON de Redis
    json_str = r.get(LED_KEY)
    if json_str:
        return json.loads(json_str)
    # Fallback si por alguna razón la clave no existe
    return {"led1": False, "led2": False}

def guardar_leds(data):
    """Convierte el diccionario a JSON y lo guarda en Redis."""
    # Convertimos el diccionario a JSON string
    json_str = json.dumps(data)
    # Guardamos el string en Redis
    r.set(LED_KEY, json_str)


@app.route("/led/status", methods=["GET"])
def led_status():
    leds = leer_leds()
    return jsonify(leds)

@app.route("/led/on/<led>", methods=["GET", "POST"])
def led_on(led):
    leds = leer_leds()
    key = f"led{led}"
    if key in leds:
        leds[key] = True
        guardar_leds(leds)
        print(f"✅ {key} encendido y guardado en Redis")
        return jsonify({"message": f"{key} encendido"}), 200
    return jsonify({"error": "LED no encontrado"}), 404

@app.route("/led/off/<led>", methods=["GET", "POST"])
def led_off(led):
    leds = leer_leds()
    key = f"led{led}"
    if key in leds:
        leds[key] = False
        guardar_leds(leds)
        print(f"🚫 {key} apagado y guardado en Redis")
        return jsonify({"message": f"{key} apagado"}), 200
    return jsonify({"error": "LED no encontrado"}), 404

@app.route("/")
def home():
    return """
    <h2>✅ Servidor Flask ESP32 - Control de LEDs (Usando Redis)</h2>
    <p>Rutas disponibles:</p>
    <ul>
        <li>/led/status</li>
        <li>/led/on/1 o /led/on/2</li>
        <li>/led/off/1 o /led/off/2</li>
    </ul>
    """

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
