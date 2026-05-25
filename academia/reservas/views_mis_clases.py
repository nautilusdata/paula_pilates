"""
views_mis_clases.py
Vista "Mis Clases" para la alumna — muestra sus packs activos y el listado
de sesiones con estado visual (próximas vs completadas).
Ahora incluye notificación segura a Telegram en el Login vía Variables de Entorno (RAM).
"""

import os  # <-- 1. Importamos 'os' para leer las variables de entorno de la RAM de GCP
import logging  # <-- 2. Buena práctica para registrar logs limpios en Cloud Logging
from datetime import date, datetime
import requests
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from .models import Pack, Sesion

# Inicializamos el logger estándar de Python/Django
logger = logging.getLogger(__name__)

def notificar_login_telegram(usuario):
    """
    Envía una notificación de login leyendo el Token y el Chat ID directamente
    desde las variables de entorno inyectadas en la RAM por Secret Manager.
    """
    # Extraemos los secretos de forma segura (Zero-Knowledge en el código)
    token_bot = os.environ.get("TELEGRAM_PILATES_LOGIN")
    chat_id = os.environ.get("TELEGRAM_USER_ID")
    
    # Control de seguridad: Si no están configuradas en GCP, evitamos que la app se caiga
    if not token_bot or not chat_id:
        logger.error("❌ Error de Seguridad Cloud: Falta configurar TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID en las variables de entorno.")
        return False

    url = f"https://api.telegram.org/bot{token_bot}/sendMessage"
    
    # Construimos el mensaje (los datos del usuario solo viven aquí en la memoria volátil)
    mensaje = f"🔑 *Alumno logueado*: {usuario.get_full_name()} email <{usuario.email}> acaba de entrar a ver sus clases."
    
    payload = {
        "chat_id": chat_id,
        "text": mensaje,
        "parse_mode": "Markdown"
    }
    
    try:
        response = requests.post(url, json=payload, timeout=5)
        if response.status_code == 200:
            return True
        else:
            logger.error(f"❌ Telegram respondió con código de error: {response.text}")
            return False
    except Exception as e:
        # Registramos el fallo técnico de conexión sin exponer variables críticas
        logger.error(f"💥 Fallo al conectar con la API de Telegram: {e}")
        return False


@login_required
def mis_clases(request):
    hoy = date.today()
    ahora = timezone.now()

    # 🔥 REVISIÓN DE SESIÓN WEB + NOTIFICACIÓN SEGURA
    # Si la variable 'login_notificado' no existe en la sesión del usuario, disparamos los eventos
    if not request.session.get('login_notificado', False):
        
        # 1. Alerta nativa y anónima en Cloud Logging (Ideal para métricas de Google Cloud)
        # Registramos solo el ID numérico para evitar la fuga de información personal (PII Leak)
        logger.info(f"USER_LOGIN_SUCCESS: El usuario con ID {request.user.pk} ha iniciado sesión.")
        
        # 2. Despacho del mensaje detallado hacia tu Telegram
        notificar_login_telegram(request.user)
        
        # Guardamos el estado en la sesión web para no repetir el aviso en cada recarga
        request.session['login_notificado'] = True 

    # --- LÓGICA DE NEGOCIO ORIGINAL (PACKS Y SESIONES) ---
    packs = (
        Pack.objects
        .filter(alumna=request.user)
        .exclude(estado='CANCELADO')
        .prefetch_related('sesiones')
        .order_by('-fecha_inicio')
    )

    packs_data = []
    proxima_global = None

    for pack in packs:
        sesiones = pack.sesiones.order_by('fecha', 'hora')

        completadas = sesiones.filter(estado='COMPLETADA').count()
        total       = sesiones.count()

        # Recuperaciones usadas en este pack
        recuperaciones_usadas = sesiones.filter(es_recupero=True).count()
        puede_recuperar_mas   = recuperaciones_usadas < 2

        proxima = sesiones.filter(fecha__gte=hoy, estado='PROGRAMADA').first()
        if proxima and (proxima_global is None or proxima.fecha < proxima_global.fecha):
            proxima_global = proxima

        sesiones_list = []
        for s in sesiones:
            es_proxima = (proxima and s.pk == proxima.pk)
            pasada     = s.fecha < hoy or s.estado == 'COMPLETADA'

            # ¿Puede recuperar esta sesión?
            puede_recuperar = False
            if s.estado == 'RECUPERAR' and s.marcada_ausente_en and puede_recuperar_mas:
                # Plazo: hasta las 12pm del día siguiente a cuando Paula marcó
                marcada_local = timezone.localtime(s.marcada_ausente_en)
                dia_siguiente = marcada_local.date() + date.resolution
                plazo = timezone.make_aware(
                    datetime.combine(dia_siguiente, datetime.min.time().replace(hour=12))
                )
                puede_recuperar = ahora < plazo

            sesiones_list.append({
                'sesion':          s,
                'es_proxima':      es_proxima,
                'pasada':          pasada,
                'puede_recuperar': puede_recuperar,
            })

        packs_data.append({
            'pack':                  pack,
            'sesiones':              sesiones_list,
            'completadas':           completadas,
            'total':                 total,
            'proxima':               proxima,
            'recuperaciones_usadas': recuperaciones_usadas,
        })

    context = {
        'packs_data':     packs_data,
        'proxima_global': proxima_global,
        'hoy':            hoy,
    }
    return render(request, 'reservas/mis_clases.html', context)