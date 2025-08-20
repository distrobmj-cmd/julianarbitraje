import requests
import time
import os
from datetime import datetime
from flask import Flask
import threading

# --- Configuración desde variables de entorno ---
TOKEN = os.getenv('TOKEN', '8369529426:AAEUR4HXafgMlOnyOyd_iA5MFQAydKRWciE')
CHAT_ID = os.getenv('CHAT_ID', '6620575663')

# Configuración del bot
PORCENTAJE_DESCUENTO = 0.02  # 2% de descuento
INTERVALO_REVISION = 60  # segundos entre revisiones de precio
INTERVALO_TRM = 3600  # actualizar TRM cada hora (3600 segundos)

# Variables globales
trm_actual = None
fecha_trm = None
ultima_actualizacion_trm = 0
ultimo_precio_alertado = None
contador_alertas = 0

# Flask para mantener el servicio vivo en Render
app = Flask(__name__)

@app.route('/')
def home():
    return f"""
    <h1>🤖 Bot TRM Alerts - ACTIVO ✅</h1>
    <h2>📊 Estado Actual:</h2>
    <ul>
        <li><strong>💰 TRM Oficial:</strong> {trm_actual:,.2f} COP ({fecha_trm if fecha_trm else 'Sin fecha'})</li>
        <li><strong>🎯 Umbral de Alerta:</strong> {(trm_actual * (1-PORCENTAJE_DESCUENTO)):,.2f} COP (-2%)</li>
        <li><strong>🚨 Alertas Enviadas:</strong> {contador_alertas}</li>
        <li><strong>⏰ Última Actualización:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</li>
        <li><strong>🔄 Próxima Actualización TRM:</strong> {max(0, int((INTERVALO_TRM - (time.time() - ultima_actualizacion_trm)) / 60))} minutos</li>
    </ul>
    <h3>🔍 Monitoreo:</h3>
    <ul>
        <li>Revisando precios cada {INTERVALO_REVISION} segundos</li>
        <li>Actualizando TRM cada {INTERVALO_TRM//60} minutos</li>
        <li>Fuente TRM: Banco de la República de Colombia</li>
    </ul>
    """

@app.route('/status')
def status():
    return {
        'status': 'active',
        'trm_actual': trm_actual,
        'fecha_trm': fecha_trm,
        'umbral_alerta': trm_actual * (1-PORCENTAJE_DESCUENTO) if trm_actual else None,
        'alertas_enviadas': contador_alertas,
        'ultima_revision': datetime.now().isoformat(),
        'proxima_actualizacion_trm_minutos': max(0, int((INTERVALO_TRM - (time.time() - ultima_actualizacion_trm)) / 60))
    }

def run_flask():
    """Ejecuta Flask para mantener el servicio vivo"""
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

def log_mensaje(mensaje):
    """Imprime mensaje con timestamp"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {mensaje}")

def enviar_mensaje(mensaje):
    """Envía mensaje a Telegram con manejo de errores"""
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        response = requests.post(
            url, 
            data={"chat_id": CHAT_ID, "text": mensaje, "parse_mode": "Markdown"},
            timeout=15
        )
        if response.status_code == 200:
            log_mensaje("✅ Mensaje enviado correctamente")
            return True
        else:
            log_mensaje(f"❌ Error enviando mensaje: {response.status_code}")
            return False
    except Exception as e:
        log_mensaje(f"❌ Error enviando mensaje: {e}")
        return False

def obtener_trm_oficial():
    """Obtiene la TRM oficial del Banco de la República con múltiples fuentes"""
    global trm_actual, fecha_trm
    
    # Fuente 1: API del Banco de la República (más confiable)
    try:
        log_mensaje("🔍 Consultando TRM del Banco de la República...")
        url = "https://www.datos.gov.co/resource/32sa-8pi3.json?$limit=1&$order=vigenciadesde DESC"
        
        response = requests.get(url, timeout=15)
        if response.status_code == 200:
            data = response.json()
            if data and len(data) > 0:
                nueva_trm = float(data[0]['valor'])
                nueva_fecha = data[0]['vigenciadesde'].split('T')[0]  # Solo la fecha
                
                if nueva_trm > 0:
                    trm_actual = nueva_trm
                    fecha_trm = nueva_fecha
                    log_mensaje(f"✅ TRM oficial obtenida: {nueva_trm:,.2f} COP (Fecha: {nueva_fecha})")
                    return True
    except Exception as e:
        log_mensaje(f"❌ Error API Banco República: {e}")
    
    # Fuente 2: API alternativa como respaldo
    try:
        log_mensaje("🔍 Intentando fuente alternativa...")
        url_alt = "https://api.exchangerate-api.com/v4/latest/USD"
        
        response = requests.get(url_alt, timeout=15)
        if response.status_code == 200:
            data = response.json()
            if 'rates' in data and 'COP' in data['rates']:
                trm_aprox = data['rates']['COP']
                if trm_aprox > 0:
                    trm_actual = trm_aprox
                    fecha_trm = "API alternativa"
                    log_mensaje(f"⚠️ TRM alternativa: {trm_aprox:,.2f} COP")
                    return True
    except Exception as e:
        log_mensaje(f"❌ Error API alternativa: {e}")
    
    # Fuente 3: Como último recurso, usar valor fijo reciente
    if trm_actual is None:
        trm_actual = 4050
        fecha_trm = "Valor por defecto"
        log_mensaje(f"⚠️ Usando TRM por defecto: {trm_actual:,.2f} COP")
        return True
    
    return False

def obtener_precio_binance():
    """Obtiene precio P2P Binance con información detallada"""
    try:
        url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
        data = {
            "asset": "USDT",
            "fiat": "COP",
            "tradeType": "BUY",
            "payTypes": ["Bancolombia", "NequiPay"],  # Múltiples métodos
            "page": 1,
            "rows": 3,
            "publisherType": None
        }
        
        response = requests.post(url, json=data, timeout=15)
        if response.status_code == 200:
            result = response.json()
            if result.get("data") and len(result["data"]) > 0:
                anuncios = result["data"]
                
                mejor_precio = float(anuncios[0]["adv"]["price"])
                vendedor = anuncios[0]["advertiser"]["nickName"]
                completados = anuncios[0]["advertiser"]["monthOrderCount"]
                tasa_completado = anuncios[0]["advertiser"]["monthFinishRate"]
                
                # Log de precios
                precios_texto = "💰 Top 3 USDT: "
                for i, anuncio in enumerate(anuncios[:3], 1):
                    precio = float(anuncio["adv"]["price"])
                    precios_texto += f"{i}.{precio:,.0f} "
                
                log_mensaje(precios_texto)
                
                return {
                    'precio': mejor_precio,
                    'vendedor': vendedor,
                    'completados': completados,
                    'tasa': tasa_completado,
                    'precios_top3': [(float(a["adv"]["price"]), a["advertiser"]["nickName"]) for a in anuncios[:3]]
                }
        
        log_mensaje("❌ No se pudo obtener datos de Binance")
        return None
        
    except Exception as e:
        log_mensaje(f"❌ Error obteniendo precio Binance: {e}")
        return None

def debe_enviar_alerta(precio_actual):
    """Determina si debe enviar alerta para evitar spam"""
    global ultimo_precio_alertado
    
    if ultimo_precio_alertado is None:
        return True
    
    # Solo alertar si el precio mejoró significativamente
    mejora = ultimo_precio_alertado - precio_actual
    return mejora >= 15

def formatear_mensaje_alerta(datos_binance, trm, umbral):
    """Formatea el mensaje de alerta con TRM oficial"""
    precio = datos_binance['precio']
    descuento_real = ((trm - precio) / trm) * 100
    ahorro_100usd = (trm - precio) * 100
    
    # Top 3 precios
    top3_texto = ""
    for i, (p, nick) in enumerate(datos_binance['precios_top3'], 1):
        descuento_p = ((trm - p) / trm) * 100
        emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉"
        top3_texto += f"{emoji} *{p:,.0f}* COP (-{descuento_p:.1f}%)\n"
    
    mensaje = f"""🚨 *¡OPORTUNIDAD USDT!* 🚨

🏛️ *TRM OFICIAL BANREP:* {trm:,.2f} COP
📅 *Fecha TRM:* {fecha_trm}
🎯 *Umbral (-2%):* {umbral:,.0f} COP

{top3_texto}
👤 *Vendedor top:* {datos_binance['vendedor']}
📊 *{datos_binance['completados']} órdenes, {datos_binance['tasa']:.1f}% éxito*

💡 *Ahorro por $100 USD: {ahorro_100usd:,.0f} COP*
📈 *Descuento real: -{descuento_real:.2f}%*
⏰ {datetime.now().strftime('%H:%M:%S')}

🔗 [Ir a Binance P2P](https://p2p.binance.com/es/trade/buy/USDT?fiat=COP&payment=Bancolombia)"""
    
    return mensaje

def mostrar_resumen_trm():
    """Muestra resumen completo de la TRM"""
    if trm_actual:
        umbral = trm_actual * (1 - PORCENTAJE_DESCUENTO)
        mensaje_resumen = f"""📊 *ACTUALIZACIÓN TRM AUTOMÁTICA*

🏛️ *TRM Oficial Banrep:* {trm_actual:,.2f} COP
📅 *Fecha:* {fecha_trm}
🎯 *Umbral alerta (-2%):* {umbral:,.0f} COP

🔄 *Próxima actualización:* {INTERVALO_TRM//60} minutos
🤖 *Bot monitoreando Binance P2P...*"""
        
        enviar_mensaje(mensaje_resumen)
        log_mensaje(f"📈 TRM mostrada: {trm_actual:,.2f} COP ({fecha_trm})")

def bot_main():
    """Función principal del bot"""
    global ultimo_precio_alertado, contador_alertas, ultima_actualizacion_trm
    
    log_mensaje("🚀 Iniciando bot TRM automático en Render...")
    
    # Obtener TRM inicial
    if obtener_trm_oficial():
        ultima_actualizacion_trm = time.time()
        mostrar_resumen_trm()
    else:
        log_mensaje("❌ No se pudo obtener TRM inicial")
        return
    
    contador_resumenes = 0
    
    while True:
        try:
            tiempo_actual = time.time()
            
            # Actualizar TRM cada hora
            if (tiempo_actual - ultima_actualizacion_trm) >= INTERVALO_TRM:
                log_mensaje("🔄 Actualizando TRM...")
                if obtener_trm_oficial():
                    ultima_actualizacion_trm = tiempo_actual
                    mostrar_resumen_trm()
            
            # Obtener precio de Binance
            datos_binance = obtener_precio_binance()
            
            if datos_binance and trm_actual:
                precio_actual = datos_binance['precio']
                umbral = trm_actual * (1 - PORCENTAJE_DESCUENTO)
                
                # Mostrar comparación cada 10 revisiones
                if contador_resumenes % 10 == 0:
                    diferencia = ((precio_actual - trm_actual) / trm_actual) * 100
                    estado = "🟢 BARATO" if precio_actual <= umbral else "🟡 NORMAL" if precio_actual < trm_actual else "🔴 CARO"
                    log_mensaje(f"📊 TRM:{trm_actual:,.0f} | USDT:{precio_actual:,.0f} | {diferencia:+.1f}% {estado}")
                
                contador_resumenes += 1
                
                # Verificar alerta
                if precio_actual <= umbral:
                    if debe_enviar_alerta(precio_actual):
                        mensaje_alerta = formatear_mensaje_alerta(datos_binance, trm_actual, umbral)
                        if enviar_mensaje(mensaje_alerta):
                            ultimo_precio_alertado = precio_actual
                            contador_alertas += 1
                            log_mensaje(f"🚨 ALERTA #{contador_alertas} ENVIADA ✅")
            else:
                log_mensaje("⚠️ Error obteniendo datos")
            
            time.sleep(INTERVALO_REVISION)
            
        except Exception as e:
            log_mensaje(f"❌ Error en loop principal: {e}")
            time.sleep(INTERVALO_REVISION)

def main():
    """Función principal que inicia Flask y el bot"""
    log_mensaje("🌟 Bot TRM Automático para Render iniciando...")
    
    # Iniciar Flask en un hilo separado
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    log_mensaje("🌐 Servidor Flask iniciado")
    
    # Esperar un poco para que Flask inicie
    time.sleep(2)
    
    # Iniciar el bot principal
    try:
        bot_main()
    except KeyboardInterrupt:
        log_mensaje("🛑 Bot detenido manualmente")
        enviar_mensaje(f"🛑 *Bot TRM Automático Detenido*\n📊 Total alertas: {contador_alertas}")
    except Exception as e:
        log_mensaje(f"❌ Error fatal: {e}")
        enviar_mensaje(f"❌ *Bot Error Fatal*\n{str(e)}")

if __name__ == "__main__":
    main()