from django.shortcuts import render, redirect
from django.contrib.auth.models import User
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from .forms import RegistroForm, PerfilForm
from .models import UserMetadata
from .models import ConfiguracionPrecio


def registro(request):
    if request.method == 'POST':
        form = RegistroForm(request.POST)
        if form.is_valid():
            user = User.objects.create_user(
                username=form.cleaned_data['email'],
                email=form.cleaned_data['email'],
                password=form.cleaned_data['password1'],
                first_name=form.cleaned_data['first_name'],
                last_name=form.cleaned_data['last_name'],
            )
            metadata = user.usermetadata
            metadata.telefono = form.cleaned_data.get('telefono', '')
            metadata.contacto_emergencia = form.cleaned_data.get('contacto_emergencia', '')
            metadata.telefono_emergencia = form.cleaned_data.get('telefono_emergencia', '')
            if form.cleaned_data.get('fecha_nacimiento'):
                metadata.fecha_nacimiento = form.cleaned_data['fecha_nacimiento']
            metadata.save()
            login(request, user)
            return redirect('dashboard')
    else:
        form = RegistroForm()
    return render(request, 'account/signup.html', {'form': form})


@login_required
def perfil(request):
    metadata = request.user.usermetadata
    if request.method == 'POST':
        form = PerfilForm(request.POST)
        if form.is_valid():
            request.user.first_name = form.cleaned_data['first_name']
            request.user.last_name = form.cleaned_data['last_name']
            request.user.save()
            metadata.telefono = form.cleaned_data.get('telefono', '')
            metadata.contacto_emergencia = form.cleaned_data.get('contacto_emergencia', '')
            metadata.telefono_emergencia = form.cleaned_data.get('telefono_emergencia', '')
            if form.cleaned_data.get('fecha_nacimiento'):
                metadata.fecha_nacimiento = form.cleaned_data['fecha_nacimiento']
            metadata.save()
            return redirect('perfil')
    else:
        form = PerfilForm(initial={
            'first_name': request.user.first_name,
            'last_name': request.user.last_name,
            'telefono': metadata.telefono,
            'contacto_emergencia': metadata.contacto_emergencia,
            'telefono_emergencia': metadata.telefono_emergencia,
            'fecha_nacimiento': metadata.fecha_nacimiento,
        })
    return render(request, 'perfil.html', {'form': form, 'metadata': metadata})


@login_required
def reservar(request):
    precio_pack12 = ConfiguracionPrecio.get('PACK12', 115_000)
    precio_pack10 = ConfiguracionPrecio.get('PACK10', 110_000)
    precio_pack8  = ConfiguracionPrecio.get('PACK8', 105_000)
    precio_pack4  = ConfiguracionPrecio.get('PACK4', 60_000)
    return render(request, 'reservar.html', {
        'precio_pack12':         precio_pack12,
        'precio_pack12_clase':   precio_pack12 // 12,
        'precio_pack10':         precio_pack10,
        'precio_pack10_clase':   precio_pack10 // 10,
        'precio_pack8':          precio_pack8,
        'precio_pack8_clase':    precio_pack8 // 8,
        'precio_pack4':          precio_pack4,
        'precio_pack4_clase':    precio_pack4 // 4,
        'precio_suelta':        ConfiguracionPrecio.get('CLASE_SUELTA', 0),
        'precio_prueba':        ConfiguracionPrecio.get('CLASE_PRUEBA', 0),
        'precio_privada':       ConfiguracionPrecio.get('PRIVADA_PACK10', 0),
        'precio_bb_full':       ConfiguracionPrecio.get('BB_FULL', 0),
        'precio_bb_semanal':    ConfiguracionPrecio.get('BB_SEMANAL', 0),
    })