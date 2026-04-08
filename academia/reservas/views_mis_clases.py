"""
views_mis_clases.py
Vista "Mis Clases" para la alumna — muestra sus packs activos y el listado
de sesiones con estado visual (próximas vs completadas).
"""

from datetime import date, datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
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
        .exclude(estado__in=['CANCELADO', 'PENDIENTE_PAGO']) # excluyendo mostrar packs huerfanos
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


@login_required
def recuperar_clase(request, sesion_id):
    """Alumna elige slot para recuperar su clase perdida."""
    hoy = date.today()
    ahora = timezone.now()

    sesion = get_object_or_404(Sesion, pk=sesion_id, pack__alumna=request.user)

    # Validar que sea recuperable
    if sesion.estado != 'RECUPERAR' or not sesion.marcada_ausente_en:
        messages.error(request, 'Esta sesión no está disponible para recuperar.')
        return redirect('mis_clases')

    # Validar plazo (antes de las 12pm del día siguiente)
    marcada_local = timezone.localtime(sesion.marcada_ausente_en)
    dia_siguiente = marcada_local.date() + date.resolution
    plazo = timezone.make_aware(
        datetime.combine(dia_siguiente, datetime.min.time().replace(hour=12))
    )
    if ahora >= plazo:
        messages.error(request, 'El plazo para recuperar esta clase ya venció.')
        return redirect('mis_clases')

    # Validar máximo 2 recuperaciones por pack
    recuperaciones_usadas = sesion.pack.sesiones.filter(es_recupero=True).count()
    if recuperaciones_usadas >= 2:
        messages.error(request, 'Ya usaste las 2 recuperaciones permitidas para este pack.')
        return redirect('mis_clases')

    # Slots disponibles — cualquier hora del día siguiente con cupo
    from .models import DIAS_SEMANA_PILATES, horas_disponibles_por_tipo
    from .models import feriados_punta_arenas
    horas_pl = horas_disponibles_por_tipo('PL')
    feriados = feriados_punta_arenas()
    slots_disponibles = []

    if dia_siguiente in feriados:
        slots_disponibles = []  # No hay clases en feriado
    else:
        for hora in horas_pl:
            cupos = Sesion.cupos_disponibles(dia_siguiente, hora)
            if cupos > 0:
                slots_disponibles.append({
                    'hora':  hora,
                    'label': f'{hora:02d}:00',
                    'cupos': cupos,
                })

    if request.method == 'POST':
        hora_str = request.POST.get('hora')
        if not hora_str or not hora_str.isdigit():
            messages.error(request, 'Elige una hora válida.')
        else:
            hora = int(hora_str)
            if Sesion.cupos_disponibles(dia_siguiente, hora) < 1:
                messages.error(request, 'Ese slot ya no tiene cupo. Elige otro.')
            else:
                # Crear sesión de recuperación con número especial
                ultimo_numero = sesion.pack.sesiones.count() + 1
                Sesion.objects.create(
                    pack        = sesion.pack,
                    fecha       = dia_siguiente,
                    hora        = hora,
                    numero      = ultimo_numero,
                    estado      = 'PROGRAMADA',
                    es_recupero = True,
                    sesion_orig = sesion,
                )
                # Marcar sesión original como ausente recuperada
                sesion.estado = 'RECUPERAR'
                sesion.save()

                messages.success(request, f'¡Clase recuperada! Te esperamos el {dia_siguiente} a las {hora:02d}:00.')
                return redirect('mis_clases')

    context = {
        'sesion':           sesion,
        'dia_siguiente':    dia_siguiente,
        'slots_disponibles': slots_disponibles,
        'plazo':            plazo,
    }
    return render(request, 'reservas/recuperar_clase.html', context)