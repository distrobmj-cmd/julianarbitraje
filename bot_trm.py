import requests
import time
import os
from datetime import datetime
from flask import Flask
import threading
import json

# --- Configuración desde variables de entorno ---
TOKEN = os.getenv('TOKEN', '8369529426:AAEUR4HXafgMlOnyOyd_iA5MFQAydKRWciE')
CHAT_ID = os.getenv('CHAT_ID', '6620575663')

# Configuración del bot
DESCUENTO_VANK = 0.01  # 1% de descuento para precio estimado VANK
INTERVALO_REVISION = 60  # segundos entre revisiones de precio
INTERVALO_TRM = 1800  # actualizar TRM cada 30 minutos (1800 segundos)
INTERVALO_REPORTE_COMPLETO = 3600  # reporte completo cada hora

# Variables globales para tracking
trm_actual = None
trm_anterior = None
fecha_trm = None
ultima_actualizacion_trm = 0
ultimo_reporte_completo = 0
contador_alertas_trm = 0
contador_reportes = 0

# Flask para mantener el servicio vivo
app = Flask(__name__)

@app.route('/')
def home():
    precio_vank = (trm_actual * (1 - DESCUENTO_VANK)) if trm_actual else 0
    return f"""
    <h1>🤖 Bot P2P USDT + TRM + VANK - ACTIVO ✅</h1>
    <h2>📊 Estado Actual:</h2>
    <ul>
        <li><strong>💰 TRM Oficial:</strong> {trm_actual:,.2f} COP ({fecha_trm if fecha_trm else 'Sin fecha'})</li>
        <li><strong>🏦 Precio Estimado VANK (-1%):</strong> {precio_vank:,.2f} COP</li>
        <li><strong>🚨 Alertas TRM:</strong> {contador_alertas_trm}</li>
        <li><strong>📊 Reportes Enviados:</strong> {contador_reportes}</li>
        <li><strong>⏰ Última Actualización:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</li>
        <li><strong>🔄 Próxima Actualización TRM:</strong> {max(0, int((INTERVALO_TRM - (time.time() - ultima_actualizacion_trm)) / 60))} minutos</li>
    </ul>
    <h3>🔍 Monitoreo:</h3>
    <ul>
        <li>Revisando precios P2P cada {INTERVALO_REVISION} segundos</li>
        <li>Actualizando TRM cada {INTERVALO_TRM//60} minutos</li>
        <li>Reportes completos cada {INTERVALO_REPORTE_COMPLETO//60} minutos</li>
        <li>Alertas automáticas cuando cambia la TRM</li>
        <li>Fuente TRM: Banco de la República de Colombia</li>
        <li>Fuente P2P: Binance Exchange</li>
    </ul>
    """

@app.route('/status')
def status():
    precio_vank = (trm_actual * (1 - DESCUENTO_VANK)) if trm_actual else 0
    return {
        'status': 'active',
        'trm_actual': trm_actual,
        'precio_vank_estimado': precio_vank,
        'fecha_trm': fecha_trm,
        'alertas_trm': contador_alertas_trm,
        'reportes_enviados': contador_reportes,
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
    """Obtiene la TRM oficial del Banco de la República"""
    global trm_actual, trm_anterior, fecha_trm
    
    try:
        log_mensaje("🔍 Consultando TRM del Banco de la República...")
        url = "https://www.datos.gov.co/resource/32sa-8pi3.json?$limit=1&$order=vigenciadesde DESC"
        
        response = requests.get(url, timeout=15)
        if response.status_code == 200:
            data = response.json()
            if data and len(data) > 0:
                nueva_trm = float(data[0]['valor'])
                nueva_fecha = data[0]['vigenciadesde'].split('T')[0]
                
                if nueva_trm > 0:
                    # Guardar TRM anterior para detectar cambios
                    trm_anterior = trm_actual
                    trm_actual = nueva_trm
                    fecha_trm = nueva_fecha
                    log_mensaje(f"✅ TRM oficial obtenida: {nueva_trm:,.2f} COP (Fecha: {nueva_fecha})")
                    
                    # Detectar cambio en TRM
                    if trm_anterior and trm_anterior != nueva_trm:
                        diferencia = nueva_trm - trm_anterior
                        porcentaje = (diferencia / trm_anterior) * 100
                        log_mensaje(f"📈 TRM CAMBIÓ: {trm_anterior:,.2f} → {nueva_trm:,.2f} ({porcentaje:+.2f}%)")
                        return 'cambio'
                    
                    return True
    except Exception as e:
        log_mensaje(f"❌ Error API Banco República: {e}")
    
    # Respaldo con API alternativa
    try:
        log_mensaje("🔍 Intentando fuente alternativa...")
        url_alt = "https://api.exchangerate-api.com/v4/latest/USD"
        
        response = requests.get(url_alt, timeout=15)
        if response.status_code == 200:
            data = response.json()
            if 'rates' in data and 'COP' in data['rates']:
                trm_aprox = data['rates']['COP']
                if trm_aprox > 0:
                    trm_anterior = trm_actual
                    trm_actual = trm_aprox
                    fecha_trm = "API alternativa"
                    log_mensaje(f"⚠️ TRM alternativa: {trm_aprox:,.2f} COP")
                    return True
    except Exception as e:
        log_mensaje(f"❌ Error API alternativa: {e}")
    
    return False

def obtener_precios_binance_p2p(trade_type="BUY"):
    """Obtiene precios de compra o venta de USDT en Binance P2P"""
    try:
        url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
        data = {
            "asset": "USDT",
            "fiat": "COP",
            "tradeType": trade_type,  # "BUY" para comprar USDT, "SELL" para vender USDT
            "payTypes": ["Bancolombia", "NequiPay", "DaviviendaPay", "BBVA", "Davivienda"],
            "page": 1,
            "rows": 10,
            "publisherType": None
        }
        
        response = requests.post(url, json=data, timeout=15)
        if response.status_code == 200:
            result = response.json()
            if result.get("data") and len(result["data"]) > 0:
                anuncios = result["data"]
                
                precios_procesados = []
                for anuncio in anuncios[:5]:  # Top 5 mejores precios
                    precio = float(anuncio["adv"]["price"])
                    vendedor = anuncio["advertiser"]["nickName"]
                    completados = anuncio["advertiser"]["monthOrderCount"]
                    tasa_completado = anuncio["advertiser"]["monthFinishRate"]
                    minimo = float(anuncio["adv"]["minSingleTransAmount"])
                    maximo = float(anuncio["adv"]["dynamicMaxSingleTransAmount"])
                    
                    precios_procesados.append({
                        'precio': precio,
                        'vendedor': vendedor,
                        'completados': completados,
                        'tasa': tasa_completado,
                        'minimo': minimo,
                        'maximo': maximo
                    })
                
                return precios_procesados
        
        return None
        
    except Exception as e:
        log_mensaje(f"❌ Error obteniendo precios Binance P2P ({trade_type}): {e}")
        return None

def formatear_precios_p2p(precios_compra, precios_venta, trm):
    """Formatea los precios P2P para mostrar en el mensaje"""
    mensaje_compra = "*📈 MEJORES PRECIOS COMPRA USDT:*\n"
    
    if precios_compra:
        for i, datos in enumerate(precios_compra, 1):
            precio = datos['precio']
            descuento_vs_trm = ((trm - precio) / trm) * 100
            emoji = "🟢" if descuento_vs_trm > 0 else "🔴"
            
            mensaje_compra += f"{emoji} *#{i} - {precio:,.0f} COP* ({descuento_vs_trm:+.1f}%)\n"
            mensaje_compra += f"   👤 {datos['vendedor']} | {datos['completados']} órdenes\n"
            mensaje_compra += f"   💰 Rango: ${datos['minimo']:,.0f} - ${datos['maximo']:,.0f}\n\n"
    else:
        mensaje_compra += "   ⚠️ No disponible\n\n"
    
    mensaje_venta = "*📉 MEJORES PRECIOS VENTA USDT:*\n"
    
    if precios_venta:
        for i, datos in enumerate(precios_venta, 1):
            precio = datos['precio']
            premium_vs_trm = ((precio - trm) / trm) * 100
            emoji = "🟢" if premium_vs_trm < 2 else "🟡" if premium_vs_trm < 4 else "🔴"
            
            mensaje_venta += f"{emoji} *#{i} - {precio:,.0f} COP* ({premium_vs_trm:+.1f}%)\n"
            mensaje_venta += f"   👤 {datos['vendedor']} | {datos['completados']} órdenes\n"
            mensaje_venta += f"   💰 Rango: ${datos['minimo']:,.0f} - ${datos['maximo']:,.0f}\n\n"
    else:
        mensaje_venta += "   ⚠️ No disponible\n\n"
    
    return mensaje_compra + mensaje_venta

def crear_mensaje_completo(precios_compra, precios_venta, es_alerta_trm=False):
    """Crea el mensaje completo con toda la información"""
    if not trm_actual:
        return None
    
    precio_vank = trm_actual * (1 - DESCUENTO_VANK)
    
    # Encabezado según el tipo de mensaje
    if es_alerta_trm:
        encabezado = f"🚨 *¡ALERTA: TRM CAMBIÓ!* 🚨\n\n"
        if trm_anterior:
            diferencia = trm_actual - trm_anterior
            porcentaje = (diferencia / trm_anterior) * 100
            direccion = "📈" if diferencia > 0 else "📉"
            encabezado += f"{direccion} *Cambio:* {trm_anterior:,.2f} → {trm_actual:,.2f} COP ({porcentaje:+.2f}%)\n\n"
    else:
        encabezado = f"📊 *REPORTE P2P USDT - COLOMBIA* 📊\n\n"
    
    # Información principal
    mensaje = f"""{encabezado}🏛️ *TRM OFICIAL:* {trm_actual:,.2f} COP
📅 *Fecha TRM:* {fecha_trm}
🏦 *Estimado VANK (-1%):* {precio_vank:,.2f} COP

"""
    
    # Precios P2P
    mensaje += formatear_precios_p2p(precios_compra, precios_venta, trm_actual)
    
    # Análisis rápido
    if precios_compra and precios_venta:
        mejor_compra = precios_compra[0]['precio']
        mejor_venta = precios_venta[0]['precio']
        spread = mejor_venta - mejor_compra
        spread_porcentaje = (spread / mejor_compra) * 100
        
        mensaje += f"📊 *ANÁLISIS RÁPIDO:*\n"
        mensaje += f"• Spread P2P: {spread:,.0f} COP ({spread_porcentaje:.1f}%)\n"
        mensaje += f"• vs VANK: Compra {((precio_vank - mejor_compra) / mejor_compra * 100):+.1f}%\n"
        mensaje += f"• Oportunidad ahorro: {max(0, trm_actual - mejor_compra):,.0f} COP por USD\n\n"
    
    # Footer
    mensaje += f"⏰ *Actualizado:* {datetime.now().strftime('%H:%M:%S')}\n"
    mensaje += f"🔗 [Ver Binance P2P](https://p2p.binance.com/es/trade/USDT?fiat=COP)"
    
    return mensaje

def enviar_alerta_cambio_trm():
    """Envía alerta cuando cambia la TRM"""
    global contador_alertas_trm
    
    log_mensaje("🚨 Enviando alerta por cambio en TRM...")
    
    # Obtener precios actuales
    precios_compra = obtener_precios_binance_p2p("BUY")
    precios_venta = obtener_precios_binance_p2p("SELL")
    
    mensaje = crear_mensaje_completo(precios_compra, precios_venta, es_alerta_trm=True)
    
    if mensaje and enviar_mensaje(mensaje):
        contador_alertas_trm += 1
        log_mensaje(f"✅ Alerta TRM #{contador_alertas_trm} enviada")
        return True
    
    return False

def enviar_reporte_completo():
    """Envía reporte completo cada hora"""
    global contador_reportes
    
    log_mensaje("📊 Enviando reporte completo...")
    
    # Obtener precios actuales
    precios_compra = obtener_precios_binance_p2p("BUY")
    precios_venta = obtener_precios_binance_p2p("SELL")
    
    mensaje = crear_mensaje_completo(precios_compra, precios_venta, es_alerta_trm=False)
    
    if mensaje and enviar_mensaje(mensaje):
        contador_reportes += 1
        log_mensaje(f"✅ Reporte completo #{contador_reportes} enviado")
        return True
    
    return False

def bot_main():
    """Función principal del bot"""
    global ultima_actualizacion_trm, ultimo_reporte_completo
    
    log_mensaje("🚀 Iniciando Bot P2P USDT + TRM + VANK...")
    
    # Obtener TRM inicial
    resultado_trm = obtener_trm_oficial()
    if resultado_trm:
        ultima_actualizacion_trm = time.time()
        ultimo_reporte_completo = time.time()
        
        # Enviar reporte inicial
        enviar_reporte_completo()
    else:
        log_mensaje("❌ No se pudo obtener TRM inicial")
        return
    
    contador_revisiones = 0
    
    while True:
        try:
            tiempo_actual = time.time()
            contador_revisiones += 1
            
            # Actualizar TRM cada 30 minutos
            if (tiempo_actual - ultima_actualizacion_trm) >= INTERVALO_TRM:
                log_mensaje("🔄 Actualizando TRM...")
                resultado_trm = obtener_trm_oficial()
                
                if resultado_trm == 'cambio':
                    # TRM cambió - enviar alerta inmediata
                    enviar_alerta_cambio_trm()
                    ultima_actualizacion_trm = tiempo_actual
                elif resultado_trm:
                    ultima_actualizacion_trm = tiempo_actual
                    log_mensaje("✅ TRM actualizada sin cambios")
            
            # Reporte completo cada hora
            if (tiempo_actual - ultimo_reporte_completo) >= INTERVALO_REPORTE_COMPLETO:
                enviar_reporte_completo()
                ultimo_reporte_completo = tiempo_actual
            
            # Log de estado cada 10 revisiones
            if contador_revisiones % 10 == 0:
                precio_vank = trm_actual * (1 - DESCUENTO_VANK) if trm_actual else 0
                log_mensaje(f"📊 Estado: TRM {trm_actual:,.2f} | VANK {precio_vank:,.2f} | Alertas TRM: {contador_alertas_trm}")
            
            time.sleep(INTERVALO_REVISION)
            
        except Exception as e:
            log_mensaje(f"❌ Error en loop principal: {e}")
            time.sleep(INTERVALO_REVISION)

def main():
    """Función principal que inicia Flask y el bot"""
    log_mensaje("🌟 Bot P2P USDT + TRM + VANK iniciando...")
    
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
        enviar_mensaje(f"🛑 *Bot P2P USDT + VANK Detenido*\n📊 Alertas TRM: {contador_alertas_trm}\n📋 Reportes: {contador_reportes}")
    except Exception as e:
        log_mensaje(f"❌ Error fatal: {e}")

if __name__ == "__main__":
    main()
