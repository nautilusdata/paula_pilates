from datetime import date, timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.http import require_http_methods, require_POST
from django.contrib import messages
from django.contrib.auth.models import User
from .models import (
    Sesion, ConfiguracionHorario, ConfiguracionGeneral,
    ConfiguracionPrecio, Pack
)
from django.utils import timezone
from django.http import JsonResponse
from django.db import transaction

def es_staff(user):
    return user.is_staff

# Color por tipo de producto — usado en ficha_alumna
COLOR_TIPO = {
    'PACK10':    'pl',
    'REDUCIDO':  'pl',
    'SUELTA':    'pl',
    'PRIVADA':   'pv',
    'BB_FULL':   'bb',
    'BB_SEMANAL':'bb',
    'PRUEBA':    'pr',
}

@login_required
@user_passes_test(es_staff, login_url='/')
def panel_principal(request):
    hoy = date.today()
    dia_str = request.GET.get('dia')
    if dia_str:
        try:
            dia_actual = date.fromisoformat(dia_str)
        except ValueError:
            dia_actual = hoy
    else:
        dia_actual = hoy

    dia_anterior  = (dia_actual - timedelta(days=1)).isoformat()
    dia_siguiente = (dia_actual + timedelta(days=1)).isoformat()

    sesiones_dia = Sesion.objects.filter(
        fecha=dia_actual,
        estado__in=['PROGRAMADA', 'RECUPERAR', 'RECUPERADA'],
    ).select_related('pack__alumna').order_by('hora')

    from collections import defaultdict
    por_hora = defaultdict(list)
    for sesion in sesiones_dia:
        por_hora[sesion.hora].append(sesion)

    horas_del_dia = sorted(por_hora.keys())

    context = {
        'dia_actual':    dia_actual,
        'dia_anterior':  dia_anterior,
        'dia_siguiente': dia_siguiente,
        'por_hora':      dict(por_hora),
        'horas_del_dia': horas_del_dia,
        'hoy':           hoy,
        'es_hoy':        dia_actual == hoy,
    }
    return render(request, 'reservas/panel_principal.html', context)


@login_required
@user_passes_test(es_staff, login_url='/')
def ficha_alumna(request, alumna_id):
    alumna = get_object_or_404(User, pk=alumna_id)
    hoy    = date.today()

    packs = (
        Pack.objects
        .filter(alumna=alumna)
        .exclude(estado='CANCELADO')
        .prefetch_related('sesiones')
        .order_by('-fecha_inicio')
    )

    packs_data    = []
    sesiones_crono = []  # vista cronológica — todas las sesiones mezcladas

    for pack in packs:
        sesiones    = pack.sesiones.order_by('fecha', 'hora')
        completadas = sesiones.filter(estado='COMPLETADA').count()
        total       = sesiones.count()
        proxima     = sesiones.filter(fecha__gte=hoy, estado='PROGRAMADA').first()
        color       = COLOR_TIPO.get(pack.tipo, 'pl')

        sesiones_list = []
        for s in sesiones:
            es_proxima = bool(proxima and s.pk == proxima.pk)
            pasada     = s.fecha < hoy or s.estado == 'COMPLETADA'
            item = {
                'sesion':    s,
                'es_proxima': es_proxima,
                'pasada':    pasada,
                'pack':      pack,
                'color':     color,
            }
            sesiones_list.append(item)
            sesiones_crono.append(item)

        packs_data.append({
            'pack':        pack,
            'sesiones':    sesiones_list,
            'completadas': completadas,
            'total':       total,
            'proxima':     proxima,
            'color':       color,
            'futuras':     futuras,
        })

    # Ordenar cronológicamente para la segunda vista
    sesiones_crono.sort(key=lambda x: (x['sesion'].fecha, x['sesion'].hora))

    context = {
        'alumna':         alumna,
        'packs_data':     packs_data,
        'sesiones_crono': sesiones_crono,
        'hoy':            hoy,
    }
    return render(request, 'reservas/ficha_alumna.html', context)


@login_required
@user_passes_test(es_staff, login_url='/')
@require_POST
def cancelar_pack(request, pack_id):
    hoy       = date.today()
    pack      = get_object_or_404(Pack, pk=pack_id)
    alumna_id = pack.alumna.pk
    alumna_nombre = pack.alumna.get_full_name()

    with transaction.atomic():
        sesiones_borradas = pack.sesiones.filter(fecha__gte=hoy).delete()[0]
        pack.estado = 'CANCELADO'
        pack.save(update_fields=['estado'])

    messages.success(
        request,
        f'Pack de {alumna_nombre} cancelado. '
        f'{sesiones_borradas} sesión(es) futura(s) eliminada(s). '
        f'El reembolso se gestiona directamente con la alumna.'
    )
    return redirect('ficha_alumna', alumna_id=alumna_id)


@login_required
@user_passes_test(es_staff, login_url='/')
@require_http_methods(["GET", "POST"])
def panel_precios(request):
    precios = ConfiguracionPrecio.objects.all().order_by('clave')
    if request.method == 'POST':
        for precio in precios:
            nuevo = request.POST.get(f'precio_{precio.clave}')
            if nuevo and nuevo.isdigit():
                precio.valor = int(nuevo)
                precio.save()
        messages.success(request, 'Precios actualizados correctamente.')
        return redirect('panel_precios')

    reformers = ConfiguracionGeneral.get('CAPACIDAD_REFORMERS', 7)
    cap_bb    = ConfiguracionGeneral.get('CAPACIDAD_BODY_BALANCE', 20)
    context   = {'precios': precios, 'reformers': reformers, 'cap_bb': cap_bb}
    return render(request, 'reservas/panel_precios.html', context)


@login_required
@user_passes_test(es_staff, login_url='/')
@require_http_methods(["GET", "POST"])
def panel_horarios(request):
    if request.method == 'POST':
        reformers = request.POST.get('reformers')
        cap_bb    = request.POST.get('cap_bb')

        if reformers and reformers.isdigit():
            obj, _ = ConfiguracionGeneral.objects.get_or_create(
                clave='CAPACIDAD_REFORMERS', defaults={'valor': 7})
            obj.valor = int(reformers)
            obj.save()

        if cap_bb and cap_bb.isdigit():
            obj, _ = ConfiguracionGeneral.objects.get_or_create(
                clave='CAPACIDAD_BODY_BALANCE', defaults={'valor': 20})
            obj.valor = int(cap_bb)
            obj.save()

        # Nuevo: un select por slot dia_hora
        for ch in ConfiguracionHorario.objects.all():
            key   = f'slot_{ch.dia}_{ch.hora}'
            valor = request.POST.get(key, '')
            if valor == '':
                ch.activo = False
                ch.save()
            elif valor != ch.tipo:
                # Cambio de tipo — actualizar
                ch.tipo   = valor
                ch.activo = True
                ch.save()
            else:
                ch.activo = True
                ch.save()

        messages.success(request, 'Horarios actualizados.')
        return redirect('panel_horarios')

    horarios    = ConfiguracionHorario.objects.all().order_by('hora', 'dia')
    reformers   = ConfiguracionGeneral.get('CAPACIDAD_REFORMERS', 7)
    cap_bb      = ConfiguracionGeneral.get('CAPACIDAD_BODY_BALANCE', 20)
    DIAS        = [(0,'Lunes'),(1,'Martes'),(2,'Miércoles'),(3,'Jueves'),(4,'Viernes'),(5,'Sábado')]
    todas_horas = sorted(set(horarios.values_list('hora', flat=True)))

    grilla = {}
    for hora in todas_horas:
        grilla[hora] = {}
        for dia_num, _ in DIAS:
            grilla[hora][dia_num] = {}

    for ch in horarios:
        grilla[ch.hora][ch.dia][ch.tipo] = ch

    for hora in todas_horas:
        for dia_num, _ in DIAS:
            if not grilla[hora][dia_num]:
                del grilla[hora][dia_num]

    context = {
        'grilla':          grilla,
        'todas_horas':     todas_horas,
        'dias_enumerados': DIAS,
        'reformers':       reformers,
        'cap_bb':          cap_bb,
    }
    return render(request, 'reservas/panel_horarios.html', context)


@login_required
@user_passes_test(es_staff, login_url='/')
def marcar_ausente(request, sesion_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)
    try:
        sesion = Sesion.objects.get(pk=sesion_id)
    except Sesion.DoesNotExist:
        return JsonResponse({'error': 'Sesión no encontrada'}, status=404)

    if sesion.estado != 'PROGRAMADA':
        return JsonResponse({'error': 'Solo se pueden marcar sesiones programadas'}, status=400)

    sesion.estado = 'RECUPERAR'
    sesion.marcada_ausente_en = timezone.now()
    sesion.save()

    return JsonResponse({'ok': True, 'alumna': sesion.pack.alumna.get_full_name(), 'sesion_id': sesion.pk})


@login_required
@user_passes_test(es_staff, login_url='/')
@require_http_methods(["GET", "POST"])
def bulk_reschedule(request):
    context = {'hoy': date.today()}
    if request.method == 'POST':
        fecha_inicio_str  = request.POST.get('fecha_inicio')
        fecha_regreso_str = request.POST.get('fecha_regreso')
        password1 = request.POST.get('password1')
        password2 = request.POST.get('password2')
        errores   = []

        if password1 != password2:
            errores.append('Las contraseñas no coinciden.')
        else:
            from allauth.account.auth_backends import AuthenticationBackend
            backend = AuthenticationBackend()
            user = backend.authenticate(request, username=request.user.email, password=password1)
            if not user:
                errores.append('Contraseña incorrecta.')

        fecha_inicio = fecha_regreso = None
        try:
            fecha_inicio  = date.fromisoformat(fecha_inicio_str)
            fecha_regreso = date.fromisoformat(fecha_regreso_str)
            if fecha_inicio >= fecha_regreso:
                errores.append('La fecha de regreso debe ser posterior a la de inicio.')
            if fecha_inicio < date.today():
                errores.append('La fecha de inicio no puede ser en el pasado.')
        except (ValueError, TypeError):
            errores.append('Fechas no válidas.')

        if errores:
            context['errores'] = errores
            return render(request, 'reservas/bulk_reschedule.html', context)

        request.session['bulk_data'] = {
            'fecha_inicio':  fecha_inicio.isoformat(),
            'fecha_regreso': fecha_regreso.isoformat(),
        }
        return redirect('bulk_reschedule_preview')

    return render(request, 'reservas/bulk_reschedule.html', context)


@login_required
@user_passes_test(es_staff, login_url='/')
@require_http_methods(["GET", "POST"])
def bulk_reschedule_preview(request):
    bulk_data = request.session.get('bulk_data')
    if not bulk_data:
        return redirect('bulk_reschedule')

    from .models import Pack, feriados_punta_arenas, DIAS_SEMANA_PILATES

    fecha_inicio  = date.fromisoformat(bulk_data['fecha_inicio'])
    fecha_regreso = date.fromisoformat(bulk_data['fecha_regreso'])

    sesiones_afectadas = Sesion.objects.filter(
        fecha__gte=fecha_inicio, estado='PROGRAMADA',
    ).select_related('pack__alumna').order_by('pack', 'fecha')

    feriados = feriados_punta_arenas()
    previews = []
    packs_procesados = set()

    for sesion in sesiones_afectadas:
        pack = sesion.pack
        if pack.pk in packs_procesados:
            continue
        packs_procesados.add(pack.pk)

        ses_pack = list(pack.sesiones.filter(
            fecha__gte=fecha_inicio, estado='PROGRAMADA'
        ).order_by('fecha'))

        if not ses_pack:
            continue

        if pack.frecuencia in DIAS_SEMANA_PILATES:
            dias = DIAS_SEMANA_PILATES[pack.frecuencia]
            nuevas_fechas = []
            cursor = fecha_regreso
            while len(nuevas_fechas) < len(ses_pack):
                if cursor.weekday() in dias and cursor not in feriados:
                    nuevas_fechas.append(cursor)
                cursor += timedelta(days=1)
        else:
            nuevas_fechas = [fecha_regreso + timedelta(days=i) for i in range(len(ses_pack))]

        previews.append({
            'alumna':  pack.alumna.get_full_name(),
            'pack':    pack.get_tipo_display(),
            'hora':    pack.hora,
            'cambios': list(zip(ses_pack, nuevas_fechas)),
        })

    context = {
        'previews':       previews,
        'fecha_inicio':   fecha_inicio,
        'fecha_regreso':  fecha_regreso,
        'total_sesiones': sesiones_afectadas.count(),
    }

    if request.method == 'POST':
        count = 0
        with transaction.atomic():
            for preview in previews:
                for sesion, nueva_fecha in preview['cambios']:
                    sesion.fecha = sesion.fecha + timedelta(days=3650)
                    sesion.save(update_fields=['fecha'])
                    count += 1
            for preview in previews:
                for sesion, nueva_fecha in preview['cambios']:
                    sesion.fecha = nueva_fecha
                    sesion.save(update_fields=['fecha'])

        del request.session['bulk_data']
        messages.success(request, f'✓ {count} sesiones reprogramadas exitosamente.')
        return redirect('panel_principal')

    return render(request, 'reservas/bulk_reschedule_preview.html', context)


def limpiar_packs_view(request):
    token = request.headers.get('X-Scheduler-Token')
    if token != 'paula-pilates-scheduler-2026':
        return JsonResponse({'error': 'No autorizado'}, status=401)
    umbral = timezone.now() - timedelta(hours=24)
    packs  = Pack.objects.filter(estado='PENDIENTE_PAGO', creado_en__lt=umbral)
    total  = packs.count()
    packs.delete()
    return JsonResponse({'eliminados': total})
