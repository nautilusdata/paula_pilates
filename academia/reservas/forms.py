from django import forms
from django.contrib.auth.models import User
from .models import UserMetadata


class RegistroForm(forms.Form):
    # ── Obligatorios ──────────────────────────────────
    first_name = forms.CharField(
        label='Nombre',
        max_length=50,
        widget=forms.TextInput(attrs={'placeholder': 'Tu nombre'})
    )
    last_name = forms.CharField(
        label='Apellido',
        max_length=50,
        widget=forms.TextInput(attrs={'placeholder': 'Tu apellido'})
    )
    email = forms.EmailField(
        label='Email',
        widget=forms.EmailInput(attrs={'placeholder': 'tu@email.com'})
    )
    password1 = forms.CharField(
        label='Contraseña',
        widget=forms.PasswordInput(attrs={'placeholder': 'Contraseña'})
    )
    password2 = forms.CharField(
        label='Confirmar contraseña',
        widget=forms.PasswordInput(attrs={'placeholder': 'Repite la contraseña'})
    )

    # ── Opcionales ────────────────────────────────────
    telefono = forms.CharField(
        label='Teléfono',
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={'placeholder': '+56 9 1234 5678'})
    )
    contacto_emergencia = forms.CharField(
        label='Nombre contacto de emergencia',
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Nombre completo'})
    )
    telefono_emergencia = forms.CharField(
        label='Teléfono de emergencia',
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={'placeholder': '+56 9 1234 5678'})
    )
    fecha_nacimiento = forms.DateField(
        label='Fecha de nacimiento',
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'})
    )

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError('Ya existe una cuenta con este email.')
        return email

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get('password1')
        p2 = cleaned_data.get('password2')
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError('Las contraseñas no coinciden.')
        return cleaned_data


class PerfilForm(forms.Form):
    first_name = forms.CharField(
        label='Nombre',
        max_length=50,
        widget=forms.TextInput(attrs={'placeholder': 'Tu nombre'})
    )
    last_name = forms.CharField(
        label='Apellido',
        max_length=50,
        widget=forms.TextInput(attrs={'placeholder': 'Tu apellido'})
    )
    telefono = forms.CharField(
        label='Teléfono',
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={'placeholder': '+56 9 1234 5678'})
    )
    contacto_emergencia = forms.CharField(
        label='Nombre contacto de emergencia',
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Nombre completo'})
    )
    telefono_emergencia = forms.CharField(
        label='Teléfono de emergencia',
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={'placeholder': '+56 9 1234 5678'})
    )
    fecha_nacimiento = forms.DateField(
        label='Fecha de nacimiento',
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'})
    )