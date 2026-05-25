import os
import logging
import requests

# 1. Configuración básica de logs para que Cloud Logging los capture
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def enviar_notificacion_telegram(mensaje):
    """
    Envía un mensaje a Telegram leyendo las credenciales de la RAM.
    GCP inyectará estas variables desde Secret Manager.
    """
    # Extraemos los secretos directamente de las variables de entorno de la RAM
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    
    # Si por alguna razón no están configuradas, evitamos que la app se caiga
    if not bot_token or not chat_id:
        logger.error("❌ Error de Seguridad: Faltan las credenciales de Telegram en la RAM.")
        return False
        
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": mensaje,
        "parse_mode": "Markdown"
    }
    
    try:
        response = requests.post(url, json=payload, timeout=5)
        if response.status_color == 200:
            logger.info("📡 Notificación enviada a Telegram exitosamente.")
            return True
        else:
            logger.error(f"❌ Telegram respondió con error: {response.text}")
            return False
    except Exception as e:
        logger.error(f"💥 Fallo al conectar con la API de Telegram: {e}")
        return False

# --- EJEMPLO DE USO EN TU FLUJO DE LOGIN ---
def manejar_login_usuario(user_id):
    """
    Simulación de la función que procesa el inicio de sesión.
    """
    # 1. Imprimimos el log anónimo usando solo el ID del usuario
    # Tu política de alertas de GCP leerá esta frase exacta para disparar el Webhook
    logger.info(f"USER_LOGIN_SUCCESS: El usuario con ID {user_id} ha ingresado al sistema.")
    
    # 2. Si quieres disparar un mensaje directo e inmediato desde el código:
    mensaje_alerta = (
        "🔑 **Nueva sinapsis de negocio**\n"
        f"Un usuario acaba de iniciar sesión.\n"
        f"• **ID Interno:** `{user_id}`\n"
        "• **Ecosistema:** Multitenant Cloud Run"
    )
    enviar_notificacion_telegram(mensaje_alerta)