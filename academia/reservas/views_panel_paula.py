from datetime import date, timedelta
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from .models import (
    Sesion, ConfiguracionHorario, ConfiguracionGeneral,
    ConfiguracionPrecio
)

# Solo Paula (staff) puede entrar al panel
def es_staff(user):
    return user.is_staff

@login_required
@user_passes_test(es_staff, login_url='/')
def panel_principal(request):
    """Vista principal del panel — calendario semanal."""
    hoy = date.today()

    # Semana actual (lunes a sábado)
    lunes = hoy - timedelta(days=hoy.weekday())
    semana_str = request.GET.get('semana')
    if semana_str:
        try:
            lunes = date.fromisoformat(semana_str)
        except ValueError:
            pass

    dias = [lunes + timedelta(days=i) for i in range(6)]  # Lun a Sáb

    # Todas las horas posibles en la grilla
    todas_horas = sorted(set(
        ConfiguracionHorario.objects.values_list('hora', flat=True)
    ))

    # Sesiones de la semana
    sesiones_semana = Sesion.objects.filter(
        fecha__range=(dias[0], dias[-1]),
        estado__in=['PROGRAMADA', 'RECUPERAR', 'RECUPERADA'],
    ).select_related('pack__alumna').order_by('fecha', 'hora')

    # Construir grilla: {hora: {dia_weekday: [sesiones]}}
    grilla = {}
    for hora in todas_horas:
        grilla[hora] = {}
        for dia in dias:
            grilla[hora][dia.weekday()] = []

    for sesion in sesiones_semana:
        hora = sesion.hora
        dia_wd = sesion.fecha.weekday()
        if hora in grilla and dia_wd in grilla[hora]:
            grilla[hora][dia_wd].append(sesion)

    # Configuración de horarios activos para mostrar tipo en grilla
    config_horarios = {}
    for ch in ConfiguracionHorario.objects.filter(activo=True):
        config_horarios[(ch.dia, ch.hora)] = ch.tipo

    context = {
        'dias':            dias,
        'todas_horas':     todas_horas,
        'grilla':          grilla,
        'config_horarios': config_horarios,
        'semana_anterior': (lunes - timedelta(weeks=1)).isoformat(),
        'semana_siguiente': (lunes + timedelta(weeks=1)).isoformat(),
        'semana_actual':   lunes.isoformat(),
        'hoy':             hoy,
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
    """Vista para activar/desactivar slots de horario."""
    if request.method == 'POST':
        # Actualizar configuración general
        reformers = request.POST.get('reformers')
        cap_bb    = request.POST.get('cap_bb')

        if reformers and reformers.isdigit():
            obj, _ = ConfiguracionGeneral.objects.get_or_create(
                clave='CAPACIDAD_REFORMERS',
                defaults={'valor': 7}
            )
            obj.valor = int(reformers)
            obj.save()

        if cap_bb and cap_bb.isdigit():
            obj, _ = ConfiguracionGeneral.objects.get_or_create(
                clave='CAPACIDAD_BODY_BALANCE',
                defaults={'valor': 20}
            )
            obj.valor = int(cap_bb)
            obj.save()

        # Actualizar horarios — los que vienen en el POST están activos
        activos = set()
        for key in request.POST:
            if key.startswith('slot_'):
                activos.add(key)

        for ch in ConfiguracionHorario.objects.all():
            key = f'slot_{ch.dia}_{ch.hora}_{ch.tipo}'
            ch.activo = key in activos
            ch.save()

        messages.success(request, 'Horarios actualizados.')
        return redirect('panel_horarios')

    horarios = ConfiguracionHorario.objects.all().order_by('hora', 'dia')
    reformers = ConfiguracionGeneral.get('CAPACIDAD_REFORMERS', 7)
    cap_bb    = ConfiguracionGeneral.get('CAPACIDAD_BODY_BALANCE', 20)

    # Construir grilla para el template
    DIAS = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb']
    TIPOS = ['PL', 'PV', 'BDB', 'TEST']
    todas_horas = sorted(set(horarios.values_list('hora', flat=True)))

    # {hora: {tipo: {dia: ConfiguracionHorario|None}}}
    grilla = {}
    for hora in todas_horas:
        grilla[hora] = {}
        for tipo in TIPOS:
            grilla[hora][tipo] = {}
            for dia in range(6):
                grilla[hora][tipo][dia] = None

    for ch in horarios:
        grilla[ch.hora][ch.tipo][ch.dia] = ch

    context = {
        'grilla':     grilla,
        'todas_horas': todas_horas,
        'tipos':      TIPOS,
        'dias':       DIAS,
        'reformers':  reformers,
        'cap_bb':     cap_bb,
    }
    return render(request, 'reservas/panel_horarios.html', context)