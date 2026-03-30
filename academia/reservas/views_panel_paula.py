from datetime import date, timedelta
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from .models import (
    Sesion, ConfiguracionHorario, ConfiguracionGeneral,
    ConfiguracionPrecio
)
from django.utils import timezone
from django.http import JsonResponse

# Solo Paula (staff) puede entrar al panel
def es_staff(user):
    return user.is_staff

@login_required
@user_passes_test(es_staff, login_url='/')
def panel_principal(request):
    """Vista principal del panel — día a día."""
    hoy = date.today()

    # Día a mostrar
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

    # Sesiones del día
    sesiones_dia = Sesion.objects.filter(
        fecha=dia_actual,
        estado__in=['PROGRAMADA', 'RECUPERAR', 'RECUPERADA'],
    ).select_related('pack__alumna').order_by('hora')

    # Agrupar por hora
    from collections import defaultdict
    por_hora = defaultdict(list)
    for sesion in sesiones_dia:
        por_hora[sesion.hora].append(sesion)

    # Ordenar horas
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
@require_http_methods(["GET", "POST"])
def panel_precios(request):
    """Vista para editar precios."""
    precios = ConfiguracionPrecio.objects.all().order_by('clave')

    if request.method == 'POST':
        for precio in precios:
            nuevo = request.POST.get(f'precio_{precio.clave}')
            if nuevo and nuevo.isdigit():
                precio.valor = int(nuevo)
                precio.save()
        messages.success(request, 'Precios actualizados correctamente.')
        return redirect('panel_precios')

    # Configuración general
    reformers = ConfiguracionGeneral.get('CAPACIDAD_REFORMERS', 7)
    cap_bb    = ConfiguracionGeneral.get('CAPACIDAD_BODY_BALANCE', 20)

    context = {
        'precios':    precios,
        'reformers':  reformers,
        'cap_bb':     cap_bb,
    }
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

        activos = set(k for k in request.POST if k.startswith('slot_'))
        for ch in ConfiguracionHorario.objects.all():
            key = f'slot_{ch.dia}_{ch.hora}_{ch.tipo}'
            ch.activo = key in activos
            ch.save()

        messages.success(request, 'Horarios actualizados.')
        return redirect('panel_horarios')

    horarios = ConfiguracionHorario.objects.all().order_by('hora', 'dia')
    reformers = ConfiguracionGeneral.get('CAPACIDAD_REFORMERS', 7)
    cap_bb    = ConfiguracionGeneral.get('CAPACIDAD_BODY_BALANCE', 20)

    DIAS = [(0,'Lunes'),(1,'Martes'),(2,'Miércoles'),(3,'Jueves'),(4,'Viernes'),(5,'Sábado')]
    todas_horas = sorted(set(horarios.values_list('hora', flat=True)))

    # {hora: {dia: {tipo: ConfiguracionHorario}}}
    grilla = {}
    for hora in todas_horas:
        grilla[hora] = {}
        for dia_num, _ in DIAS:
            grilla[hora][dia_num] = {}

    for ch in horarios:
        grilla[ch.hora][ch.dia][ch.tipo] = ch

    # Eliminar dias sin ningun tipo
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
    """Paula marca una alumna como ausente desde su panel."""
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

    return JsonResponse({
        'ok': True,
        'alumna': sesion.pack.alumna.get_full_name(),
        'sesion_id': sesion.pk,
    })