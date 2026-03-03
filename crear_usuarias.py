import os
import django
import sys

# Ajusta si es necesario
sys.path.insert(0, '/home/carl/paula_pilates/academia')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'academia.settings')
django.setup()

from django.contrib.auth.models import User
from reservas.models import UserMetadata
from datetime import date
import random

usuarias = [
    # (first_name, last_name, telefono, contacto_emergencia, telefono_emergencia, fecha_nacimiento)
    ("Alejandra", "Vodanovic", "56912345601", "Carlos Vodanovic", "56912345641", date(1988, 3, 12)),
    ("Valentina", "Antunovic", "56912345602", "Pedro Antunovic", "56912345642", date(1992, 7, 24)),
    ("Francisca", "Casic", "56912345603", "Luis Casic", "56912345643", date(1985, 11, 5)),
    ("Catalina", "Zimunovic", "56912345604", "Jorge Zimunovic", "56912345644", date(1990, 1, 18)),
    ("Isadora", "Vodanovic", "56912345605", "Andrés Vodanovic", "56912345645", date(1995, 6, 30)),
    ("Constanza", "Antunovic", "56912345606", "Marco Antunovic", "56912345646", date(1987, 9, 14)),
    ("Fernanda", "Casic", "56912345607", "Roberto Casic", "56912345647", date(1993, 4, 22)),
    ("Javiera", "Zimunovic", "56912345608", "Felipe Zimunovic", "56912345648", date(1991, 8, 3)),
    ("Renata", "Vodanovic", "56912345609", "Diego Vodanovic", "56912345649", date(1986, 2, 17)),
    ("Sofía", "Antunovic", "56912345610", "Matías Antunovic", "56912345650", date(1994, 12, 9)),
    ("Camila", "González", "56912345611", "Juan González", "56912345651", date(1989, 5, 28)),
    ("Daniela", "Muñoz", "56912345612", "Ricardo Muñoz", "56912345652", date(1996, 10, 7)),
    ("Bárbara", "Rojas", "56912345613", "Pablo Rojas", "56912345653", date(1984, 3, 19)),
    ("Paulina", "Fuentes", "56912345614", "Cristian Fuentes", "56912345654", date(1990, 7, 11)),
    ("Andrea", "Morales", "56912345615", "Sebastián Morales", "56912345655", date(1988, 1, 25)),
    ("Lorena", "Casic", "56912345616", "Alberto Casic", "56912345656", date(1993, 6, 4)),
    ("Tamara", "Zimunovic", "56912345617", "Gonzalo Zimunovic", "56912345657", date(1997, 9, 16)),
    ("Ximena", "Pérez", "56912345618", "Manuel Pérez", "56912345658", date(1985, 11, 30)),
    ("Patricia", "Soto", "56912345619", "Eduardo Soto", "56912345659", date(1982, 4, 8)),
    ("Verónica", "Vodanovic", "56912345620", "Hernán Vodanovic", "56912345660", date(1991, 2, 21)),
    ("Marcela", "Antunovic", "56912345621", "Rodrigo Antunovic", "56912345661", date(1987, 8, 13)),
    ("Carolina", "Castro", "56912345622", "Ignacio Castro", "56912345662", date(1994, 5, 2)),
    ("Natalia", "Vargas", "56912345623", "Alejandro Vargas", "56912345663", date(1989, 12, 26)),
    ("Isabel", "Casic", "56912345624", "Francisco Casic", "56912345664", date(1992, 3, 15)),
    ("Gabriela", "Zimunovic", "56912345625", "Daniel Zimunovic", "56912345665", date(1986, 7, 7)),
    ("Paola", "Flores", "56912345626", "Tomás Flores", "56912345666", date(1995, 10, 20)),
    ("Roxana", "Torres", "56912345627", "Nicolás Torres", "56912345667", date(1983, 1, 9)),
    ("Yasna", "Vodanovic", "56912345628", "Claudio Vodanovic", "56912345668", date(1990, 6, 18)),
    ("Mónica", "Antunovic", "56912345629", "Víctor Antunovic", "56912345669", date(1988, 4, 3)),
    ("Angélica", "Ramírez", "56912345630", "Oscar Ramírez", "56912345670", date(1993, 9, 27)),
    ("Susana", "Casic", "56912345631", "Hugo Casic", "56912345671", date(1984, 2, 14)),
    ("Viviana", "Zimunovic", "56912345632", "Esteban Zimunovic", "56912345672", date(1991, 7, 6)),
    ("Alejandra", "Silva", "56912345633", "Mauricio Silva", "56912345673", date(1996, 11, 23)),
    ("Ingrid", "Vodanovic", "56912345634", "Patricio Vodanovic", "56912345674", date(1987, 5, 10)),
    ("Fabiola", "Antunovic", "56912345635", "Antonio Antunovic", "56912345675", date(1992, 8, 29)),
    ("Claudia", "Medina", "56912345636", "Ramón Medina", "56912345676", date(1985, 3, 1)),
    ("Elena", "Casic", "56912345637", "Julio Casic", "56912345677", date(1994, 10, 12)),
    ("Rosa", "Zimunovic", "56912345638", "Miguel Zimunovic", "56912345678", date(1989, 1, 31)),
    ("Alejandra", "Navarro", "56912345639", "Alfredo Navarro", "56912345679", date(1986, 6, 22)),
    ("Pilar", "Vodanovic", "56912345640", "Sergio Vodanovic", "56912345680", date(1993, 4, 5)),
]

def generar_email(first_name, last_name):
    # Quitar tildes básicos
    reemplazos = {'á':'a','é':'e','í':'i','ó':'o','ú':'u','ñ':'n','ü':'u'}
    nombre = first_name.lower()
    apellido = last_name.lower()
    for k, v in reemplazos.items():
        nombre = nombre.replace(k, v)
        apellido = apellido.replace(k, v)
    parte = nombre[0] + apellido[0]
    dominio = apellido[0] + nombre[0]
    return f"{parte}@{dominio}.cl"

creadas = 0
for first_name, last_name, telefono, contacto_emergencia, telefono_emergencia, fecha_nacimiento in usuarias:
    email = generar_email(first_name, last_name)
    username = email.split('@')[0] + str(random.randint(1,99))
    
    if User.objects.filter(email=email).exists():
        print(f"Ya existe: {email}")
        continue

    user = User.objects.create_user(
        username=username,
        email=email,
        password='Pilates2024!',
        first_name=first_name,
        last_name=last_name,
    )

    # El signal crea el UserMetadata, solo actualizamos los campos extra
    user.usermetadata.telefono = telefono
    user.usermetadata.contacto_emergencia = contacto_emergencia
    user.usermetadata.telefono_emergencia = telefono_emergencia
    user.usermetadata.fecha_nacimiento = fecha_nacimiento
    user.usermetadata.save()

    print(f"✓ {first_name} {last_name} — {email}")
    creadas += 1

print(f"\n{creadas} usuarias creadas.")
