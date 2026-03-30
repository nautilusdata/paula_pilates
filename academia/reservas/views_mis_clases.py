"""
views_mis_clases.py
Vista "Mis Clases" para la alumna — muestra sus packs activos y el listado
de sesiones con estado visual (próximas vs completadas).
"""

from datetime import date, datetime
from django.utils import timezone
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from .models import Pack, Sesion


@login_required
def mis_clases(request):
    hoy = date.today()
    ahora = timezone.now()

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
                dia_siguiente = s.marcada_ausente_en.date() + date.resolution
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