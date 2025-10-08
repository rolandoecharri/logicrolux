import os
import time
import requests
from datetime import datetime, timedelta
from flask import Flask, render_template_string, jsonify
from threading import Thread
from dotenv import load_dotenv
import xml.etree.ElementTree as ET
from xml.dom import minidom
import json
import logging
from logging.handlers import RotatingFileHandler

# Cargar variables de entorno
load_dotenv()

app = Flask(__name__)

# Configurar logging
def setup_logging():
    """Configura el sistema de logging para los POST"""
    # Logger para POST requests
    post_logger = logging.getLogger('post_requests')
    post_logger.setLevel(logging.INFO)
    
    # Handler con rotación de archivos (máximo 10MB, mantener 5 archivos)
    handler = RotatingFileHandler(
        'logs/post_requests.log',
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    
    # Formato del log
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    handler.setFormatter(formatter)
    post_logger.addHandler(handler)
    
    return post_logger

post_logger = setup_logging()

# Variables globales para almacenar resultados
latest_soap_response = ""
latest_post_results = []
last_update = ""

def get_imeis():
    """Lee los IMEIs del archivo imeis.data"""
    try:
        with open('imeis.data', 'r') as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        return []

def format_xml(xml_string):
    """Formatea XML para que sea legible"""
    try:
        dom = minidom.parseString(xml_string)
        return dom.toprettyxml(indent="  ")
    except:
        return xml_string

def create_soap_request():
    """Crea el request SOAP con fechas actuales"""
    login = os.getenv('LOGIN', '')
    password = os.getenv('PASSWORD', '')
    
    # Fechas: endDate = ahora, startDate = 15 minutos atrás
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(minutes=15)
    
    start_date_str = start_date.strftime('%Y-%m-%dT%H:%M:%SZ')
    end_date_str = end_date.strftime('%Y-%m-%dT%H:%M:%SZ')
    
    imeis = get_imeis()
    device_ids_xml = '\n         '.join([f'<deviceIds>{imei}</deviceIds>' for imei in imeis])
    
    soap_request = f'''<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:tem="http://tempuri.org">
   <soapenv:Header>
      <tem:authentication>
         <login>{login}</login>
         <password>{password}</password>
      </tem:authentication>
   </soapenv:Header>
   <soapenv:Body>
      <tem:dataRequest>
         {device_ids_xml}
         <startDate>{start_date_str}</startDate>
         <endDate>{end_date_str}</endDate>
      </tem:dataRequest>
   </soapenv:Body>
</soapenv:Envelope>'''
    
    return soap_request

def parse_soap_response(xml_response):
    """Parsea la respuesta SOAP y extrae los datos de posición, agrupando por unitPlate y tomando solo la fecha más reciente"""
    positions_by_plate = {}
    
    try:
        root = ET.fromstring(xml_response)
        
        # Buscar todos los elementos de posición
        for item in root.iter():
            if 'unitPlate' in item.tag or any(child.tag.endswith('unitPlate') for child in item):
                position = {}
                for child in item:
                    tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                    position[tag] = child.text
                
                if position and 'unitPlate' in position and 'dateGps' in position:
                    plate = position['unitPlate']
                    date_gps = position['dateGps']
                    
                    try:
                        # Convertir fecha a datetime para comparar
                        current_date = datetime.fromisoformat(date_gps.replace('Z', '+00:00'))
                        
                        # Si no existe esta patente o la fecha es más reciente, actualizar
                        if plate not in positions_by_plate:
                            positions_by_plate[plate] = {
                                'data': position,
                                'datetime': current_date
                            }
                        else:
                            if current_date > positions_by_plate[plate]['datetime']:
                                positions_by_plate[plate] = {
                                    'data': position,
                                    'datetime': current_date
                                }
                    except Exception as e:
                        post_logger.warning(f"Error parseando fecha para {plate}: {e}")
                        continue
        
        # Extraer solo los datos de posición (sin el datetime auxiliar)
        latest_positions = [item['data'] for item in positions_by_plate.values()]
        
        post_logger.info(f"Total de registros encontrados: {len(latest_positions)}")
        for plate, data in positions_by_plate.items():
            post_logger.info(f"  - {plate}: {data['datetime'].strftime('%Y-%m-%d %H:%M:%S')}")
        
        return latest_positions
        
    except Exception as e:
        post_logger.error(f"Error parseando respuesta SOAP: {e}")
        print(f"Error parseando respuesta: {e}")
        return []

def send_position_post(position_data):
    """Envía un POST con los datos de posición y registra en el log"""
    try:
        # Convertir fechaHora al formato requerido (YYYYMMDDHHmmss)
        fecha_hora = position_data.get('dateGps', '')
        if fecha_hora:
            try:
                dt = datetime.fromisoformat(fecha_hora.replace('Z', '+00:00'))
                fecha_hora = dt.strftime('%Y%m%d%H%M%S')
            except:
                fecha_hora = datetime.now().strftime('%Y%m%d%H%M%S')
        
        payload = {
            "eventoId": 0,
            "patente": position_data.get('unitPlate', ''),
            "fechaHora": fecha_hora,
            "latitud": float(position_data.get('latitude', 0)),
            "longitud": float(position_data.get('longitude', 0)),
            "velocidad": int(float(position_data.get('speedGps', 0))),
            "curso": 0
        }
        
        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'Apache-HttpClient/4.5.5 (Java/17.0.12)'
        }
        
        # Log del POST que se va a enviar
        post_logger.info(f"=== ENVIANDO POST ===")
        post_logger.info(f"URL: http://api.logictracker.com:8081/api/reception/positions/genericReception")
        post_logger.info(f"Payload: {json.dumps(payload, indent=2)}")
        
        response = requests.post(
            'http://api.logictracker.com:8081/api/reception/positions/genericReception',
            json=payload,
            headers=headers,
            timeout=10
        )
        
        result = {
            'payload': payload,
            'status_code': response.status_code,
            'response': response.text,
            'success': response.status_code == 200
        }
        
        # Log de la respuesta
        if result['success']:
            post_logger.info(f"✅ POST EXITOSO - Status: {response.status_code}")
            post_logger.info(f"Respuesta: {response.text}")
        else:
            post_logger.warning(f"⚠️ POST FALLIDO - Status: {response.status_code}")
            post_logger.warning(f"Respuesta: {response.text}")
        
        post_logger.info(f"{'='*50}\n")
        
        return result
        
    except Exception as e:
        error_msg = str(e)
        post_logger.error(f"❌ ERROR EN POST")
        post_logger.error(f"Payload: {json.dumps(position_data, indent=2)}")
        post_logger.error(f"Error: {error_msg}")
        post_logger.error(f"{'='*50}\n")
        
        return {
            'payload': position_data,
            'error': error_msg,
            'success': False
        }

def execute_soap_request():
    """Ejecuta el request SOAP y procesa la respuesta"""
    global latest_soap_response, latest_post_results, last_update
    
    try:
        post_logger.info(f"\n{'#'*60}")
        post_logger.info(f"### INICIANDO CICLO DE REQUESTS SOAP ###")
        post_logger.info(f"{'#'*60}\n")
        
        soap_request = create_soap_request()
        
        headers = {
            'Content-Type': 'text/xml; charset=utf-8',
            'SOAPAction': ''
        }
        
        response = requests.post(
            'https://soap.us.navixy.com/LocationDataService',
            data=soap_request,
            headers=headers,
            timeout=30
        )
        
        latest_soap_response = format_xml(response.text)
        last_update = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        post_logger.info(f"SOAP Request exitoso - Status: {response.status_code}")
        
        # Parsear respuesta y obtener solo las posiciones más recientes por patente
        positions = parse_soap_response(response.text)
        post_logger.info(f"Posiciones más recientes por patente: {len(positions)}\n")
        
        latest_post_results = []
        
        for idx, position in enumerate(positions, 1):
            post_logger.info(f"--- Procesando posición {idx}/{len(positions)} ---")
            result = send_position_post(position)
            latest_post_results.append(result)
        
        post_logger.info(f"\n{'#'*60}")
        post_logger.info(f"### CICLO COMPLETADO - {len(positions)} posiciones procesadas ###")
        post_logger.info(f"{'#'*60}\n\n")
        
    except Exception as e:
        error_msg = f"Error en SOAP request: {str(e)}"
        latest_soap_response = error_msg
        last_update = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        post_logger.error(error_msg)

def background_task():
    """Tarea en segundo plano que ejecuta el request cada minuto"""
    while True:
        execute_soap_request()
        time.sleep(60)  # Esperar 1 minuto

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>SOAP Monitor - LOGICROLUX</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 20px;
            background-color: #f5f5f5;
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
            background-color: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        h1 {
            color: #333;
        }
        .controls {
            margin: 20px 0;
        }
        button {
            padding: 10px 20px;
            font-size: 16px;
            cursor: pointer;
            background-color: #4CAF50;
            color: white;
            border: none;
            border-radius: 4px;
            margin-right: 10px;
        }
        button:hover {
            background-color: #45a049;
        }
        button.paused {
            background-color: #f44336;
        }
        button.secondary {
            background-color: #2196F3;
        }
        button.secondary:hover {
            background-color: #0b7dda;
        }
        .info {
            margin: 10px 0;
            color: #666;
        }
        .section {
            margin: 20px 0;
            padding: 15px;
            background-color: #f9f9f9;
            border-radius: 4px;
        }
        pre {
            background-color: #272822;
            color: #f8f8f2;
            padding: 15px;
            border-radius: 4px;
            overflow-x: auto;
            white-space: pre-wrap;
            word-wrap: break-word;
        }
        .post-result {
            margin: 10px 0;
            padding: 10px;
            border-left: 4px solid #4CAF50;
            background-color: #f0f0f0;
        }
        .post-result.error {
            border-left-color: #f44336;
        }
        .post-payload {
            background-color: #e8e8e8;
            padding: 10px;
            margin: 5px 0;
            border-radius: 4px;
            font-family: monospace;
        }
        .log-info {
            background-color: #e3f2fd;
            padding: 10px;
            border-radius: 4px;
            margin: 10px 0;
        }
        .warning-info {
            background-color: #fff3cd;
            padding: 10px;
            border-radius: 4px;
            margin: 10px 0;
            border-left: 4px solid #ffc107;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🔄 SOAP Monitor - LOGICROLUX</h1>
        
        <div class="controls">
            <button id="pauseBtn" onclick="togglePause()">⏸️ Pausar Auto-Refresh</button>
            <button onclick="manualRefresh()">🔄 Actualizar Ahora</button>
            <button class="secondary" onclick="window.open('/logs', '_blank')">📋 Ver Logs</button>
        </div>
        
        <div class="log-info">
            📝 <strong>Logs guardados en:</strong> post_requests.log (rotación automática cada 10MB)
        </div>
        
        <div class="warning-info">
            ⚠️ <strong>Filtro activo:</strong> Solo se procesa la posición más reciente por patente
        </div>
        
        <div class="info">
            <strong>Última actualización:</strong> <span id="lastUpdate">{{ last_update }}</span><br>
            <strong>Auto-refresh:</strong> cada 30 segundos<br>
            <strong>Request SOAP:</strong> cada 60 segundos
        </div>
        
        <div class="section">
            <h2>📡 Respuesta SOAP</h2>
            <pre id="soapResponse">{{ soap_response }}</pre>
        </div>
        
        <div class="section">
            <h2>📤 Resultados POST ({{ post_count }} registros - solo más recientes)</h2>
            <div id="postResults">
                {% for result in post_results %}
                <div class="post-result {% if not result.success %}error{% endif %}">
                    <strong>{% if result.success %}✅{% else %}❌{% endif %} 
                    {{ result.payload.get('patente', 'N/A') }}</strong>
                    <div class="post-payload">
                        <strong>Payload:</strong><br>
                        {{ result.payload | tojson(indent=2) }}
                    </div>
                    <div>
                        <strong>Status:</strong> {{ result.get('status_code', 'Error') }}<br>
                        <strong>Respuesta:</strong> {{ result.get('response', result.get('error', 'N/A')) }}
                    </div>
                </div>
                {% endfor %}
            </div>
        </div>
    </div>
    
    <script>
        let isPaused = false;
        let refreshInterval;
        
        function togglePause() {
            isPaused = !isPaused;
            const btn = document.getElementById('pauseBtn');
            if (isPaused) {
                btn.textContent = '▶️ Reanudar Auto-Refresh';
                btn.classList.add('paused');
                clearInterval(refreshInterval);
            } else {
                btn.textContent = '⏸️ Pausar Auto-Refresh';
                btn.classList.remove('paused');
                startAutoRefresh();
            }
        }
        
        function manualRefresh() {
            location.reload();
        }
        
        function startAutoRefresh() {
            refreshInterval = setInterval(() => {
                if (!isPaused) {
                    location.reload();
                }
            }, 30000);
        }
        
        // Iniciar auto-refresh al cargar la página
        startAutoRefresh();
    </script>
</body>
</html>
'''

LOGS_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>Logs - LOGICROLUX</title>
    <style>
        body {
            font-family: 'Courier New', monospace;
            margin: 20px;
            background-color: #1e1e1e;
            color: #d4d4d4;
        }
        .container {
            max-width: 1600px;
            margin: 0 auto;
        }
        h1 {
            color: #4CAF50;
        }
        pre {
            background-color: #252526;
            padding: 20px;
            border-radius: 4px;
            overflow-x: auto;
            white-space: pre-wrap;
            word-wrap: break-word;
            line-height: 1.5;
        }
        .controls {
            margin: 20px 0;
        }
        button {
            padding: 10px 20px;
            font-size: 16px;
            cursor: pointer;
            background-color: #4CAF50;
            color: white;
            border: none;
            border-radius: 4px;
            margin-right: 10px;
        }
        button:hover {
            background-color: #45a049;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>📋 Logs de POST Requests</h1>
        <div class="controls">
            <button onclick="location.reload()">🔄 Actualizar</button>
            <button onclick="window.close()">❌ Cerrar</button>
        </div>
        <pre>{{ logs }}</pre>
    </div>
</body>
</html>
'''

@app.route('/')
def index():
    return render_template_string(
        HTML_TEMPLATE,
        soap_response=latest_soap_response,
        post_results=latest_post_results,
        post_count=len(latest_post_results),
        last_update=last_update
    )

@app.route('/logs')
def view_logs():
    """Muestra el contenido del archivo de logs"""
    try:
        with open('logs/post_requests.log', 'r', encoding='utf-8') as f:
            logs = f.read()
        if not logs:
            logs = "No hay logs disponibles aún."
    except FileNotFoundError:
        logs = "Archivo de logs no encontrado."
    
    return render_template_string(LOGS_TEMPLATE, logs=logs)

@app.route('/api/status')
def status():
    return jsonify({
        'last_update': last_update,
        'soap_response': latest_soap_response,
        'post_results': latest_post_results
    })

if __name__ == '__main__':
    # Iniciar tarea en segundo plano
    thread = Thread(target=background_task, daemon=True)
    thread.start()
    
    # Ejecutar una vez al inicio
    post_logger.info("="*60)
    post_logger.info("🚀 APLICACIÓN INICIADA")
    post_logger.info("="*60 + "\n")
    execute_soap_request()
    
    # Iniciar servidor web
    print("🚀 Servidor iniciado en http://localhost:5000")
    print("📋 Logs disponibles en: post_requests.log")
    app.run(host='0.0.0.0', port=5000, debug=False)