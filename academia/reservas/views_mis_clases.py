"""
views_mis_clases.py
Vista "Mis Clases" para la alumna — muestra sus packs activos y el listado
de sesiones con estado visual (próximas vs completadas).
"""

from datetime import date
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from .models import Pack, Sesion


@login_required
def mis_clases(request):
    hoy = date.today()

    # Packs de la alumna, ordenados por más reciente
    packs = (
        Pack.objects
        .filter(alumna=request.user)
        .exclude(estado='CANCELADO')
        .prefetch_related('sesiones')
        .order_by('-fecha_inicio')
    )

    packs_data = []
    proxima_global = None  # la próxima clase más cercana de todos los packs

    for pack in packs:
        sesiones = pack.sesiones.order_by('fecha', 'hora')

        completadas  = sesiones.filter(estado='COMPLETADA').count()
        programadas  = sesiones.filter(estado='PROGRAMADA').count()
        total        = sesiones.count()

        # Próxima sesión de este pack
        proxima = sesiones.filter(fecha__gte=hoy, estado='PROGRAMADA').first()
        if proxima and (proxima_global is None or proxima.fecha < proxima_global.fecha):
            proxima_global = proxima

        # Construir lista de sesiones con flags para el template
        sesiones_list = []
        for s in sesiones:
            es_proxima = (proxima and s.pk == proxima.pk)
            pasada     = s.fecha < hoy or s.estado == 'COMPLETADA'
            sesiones_list.append({
                'sesion':     s,
                'es_proxima': es_proxima,
                'pasada':     pasada,
            })

        packs_data.append({
            'pack':        pack,
            'sesiones':    sesiones_list,
            'completadas': completadas,
            'programadas': programadas,
            'total':       total,
            'proxima':     proxima,
            'progreso':    range(total),          # para iterar en template
            'hechas_idx':  range(completadas),    # puntos rellenos
        })

    context = {
        'packs_data':      packs_data,
        'proxima_global':  proxima_global,
        'hoy':             hoy,
    }
    return render(request, 'reservas/mis_clases.html', context)
