from django.shortcuts import render, redirect
from django.contrib.auth.models import User
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from .forms import RegistroForm, PerfilForm
from .models import UserMetadata


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