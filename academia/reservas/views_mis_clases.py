"""
views_mis_clases.py
Vista "Mis Clases" para la alumna — muestra sus packs activos y el listado
de sesiones con estado visual (próximas vs completadas).
Ahora incluye notificación a Telegram en el Login.
"""

from datetime import date, datetime
import requests  # <-- 1. Importamos requests para Telegram
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from .models import Pack, Sesion

# 2. Tu función para conectar con Telegram
def notificar_login_telegram(usuario):
    token_bot = "TU_TOKEN_DE_TELEGRAM_AQUÍ"
    chat_id = "TU_ID_DE_CHAT_AQUÍ"
    url = f"https://api.telegram.org/bot{token_bot}/sendMessage"
    
    mensaje = f"✅ *Alumno logueado*:\nEl usuario *{usuario.username}* ({usuario.email}) acaba de entrar a ver sus clases."
    
    payload = {
        "chat_id": chat_id,
        "text": mensaje,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"Error enviando a Telegram: {e}")


@login_required
def mis_clases(request):
    hoy = date.today()
    ahora = timezone.now()

    # 3. 🔥 TRUCO: Revisamos si es la primera vez que entra en esta sesión web
    # Si la variable 'login_notificado' no existe en la sesión del usuario, enviamos el Telegram
    if not request.session.get('login_notificado', False):
        notificar_login_telegram(request.user)
        request.session['login_notificado'] = True # Guardamos que ya avisamos para no repetir

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