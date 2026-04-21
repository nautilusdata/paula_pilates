"""
Management command para insertar usuarias de prueba.

Ubicación en el proyecto:
    reservas/management/commands/crear_usuarias_prueba.py

Uso:
    python manage.py crear_usuarias_prueba
    python manage.py crear_usuarias_prueba --dry-run    # solo muestra, no inserta
    python manage.py crear_usuarias_prueba --password MiClave2026!
"""

from datetime import date
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.db import transaction
from reservas.models import UserMetadata   # ajusta si tu app se llama distinto


# ── Formato de email ───────────────────────────────────────────────────────────
# Alejandra Navarro  →  an@na.cl
# (primera letra nombre)(primera letra apellido) @ (primera letra apellido)(primera letra nombre).cl

def _normalizar(texto: str) -> str:
    """Minúsculas sin tildes para la parte del email."""
    reemplazos = str.maketrans('áéíóúàèìòùäëïöüñ', 'aeiouaeiouaeioun')
    return texto.lower().translate(reemplazos)


def generar_email(nombre: str, apellido: str, usados: set) -> str:
    n = _normalizar(nombre)[0]
    a = _normalizar(apellido)[0]
    base_local   = f"{n}{a}"          # ej. "an"
    base_dominio = f"{a}{n}"          # ej. "na"
    candidato = f"{base_local}@{base_dominio}.cl"

    if candidato not in usados:
        return candidato

    # Colisión → agregar sufijo numérico al local
    i = 2
    while True:
        candidato = f"{base_local}{i}@{base_dominio}.cl"
        if candidato not in usados:
            return candidato
        i += 1


# ── Datos de prueba ────────────────────────────────────────────────────────────
USUARIAS = [
    # (first_name, last_name, telefono, contacto_emergencia, telefono_emergencia, fecha_nacimiento)
    ("Alejandra", "Vodanovic", "56912345601", "Carlos Vodanovic",   "56912345641", date(1988,  3, 12)),
    ("Valentina", "Antunovic", "56912345602", "Pedro Antunovic",    "56912345642", date(1992,  7, 24)),
    ("Francisca", "Casic",     "56912345603", "Luis Casic",         "56912345643", date(1985, 11,  5)),
    ("Catalina",  "Zimunovic", "56912345604", "Jorge Zimunovic",    "56912345644", date(1990,  1, 18)),
    ("Isadora",   "Vodanovic", "56912345605", "Andrés Vodanovic",   "56912345645", date(1995,  6, 30)),
    ("Constanza", "Antunovic", "56912345606", "Marco Antunovic",    "56912345646", date(1987,  9, 14)),
    ("Ximena",    "Casic",     "56912345607", "Roberto Casic",      "56912345647", date(1993,  4, 22)),
    ("Javiera",   "Zimunovic", "56912345608", "Felipe Zimunovic",   "56912345648", date(1991,  8,  3)),
    ("Renata",    "Vodanovic", "56912345609", "Diego Vodanovic",    "56912345649", date(1986,  2, 17)),
    ("Sofía",     "Antunovic", "56912345610", "Matías Antunovic",   "56912345650", date(1994, 12,  9)),
    ("Camila",    "González",  "56912345611", "Juan González",      "56912345651", date(1989,  5, 28)),
    ("Daniela",   "Muñoz",     "56912345612", "Ricardo Muñoz",      "56912345652", date(1996, 10,  7)),
    ("Bárbara",   "Rojas",     "56912345613", "Pablo Rojas",        "56912345653", date(1984,  3, 19)),
    ("Paulina",   "Fuentes",   "56912345614", "Cristian Fuentes",   "56912345654", date(1990,  7, 11)),
    ("Andrea",    "Morales",   "56912345615", "Sebastián Morales",  "56912345655", date(1988,  1, 25)),
    ("Lorena",    "Casic",     "56912345616", "Alberto Casic",      "56912345656", date(1993,  6,  4)),
    ("Tamara",    "Zimunovic", "56912345617", "Gonzalo Zimunovic",  "56912345657", date(1997,  9, 16)),
    ("Ximena",    "Pérez",     "56912345618", "Manuel Pérez",       "56912345658", date(1985, 11, 30)),
    ("Patricia",  "Soto",      "56912345619", "Eduardo Soto",       "56912345659", date(1982,  4,  8)),
    ("Verónica",  "Vodanovic", "56912345620", "Hernán Vodanovic",   "56912345660", date(1991,  2, 21)),
    ("Marcela",   "Antunovic", "56912345621", "Rodrigo Antunovic",  "56912345661", date(1987,  8, 13)),
    ("Carolina",  "Castro",    "56912345622", "Ignacio Castro",     "56912345662", date(1994,  5,  2)),
    ("Natalia",   "Vargas",    "56912345623", "Alejandro Vargas",   "56912345663", date(1989, 12, 26)),
    ("Isabel",    "Casic",     "56912345624", "Francisco Casic",    "56912345664", date(1992,  3, 15)),
    ("Gabriela",  "Zimunovic", "56912345625", "Daniel Zimunovic",   "56912345665", date(1986,  7,  7)),
    ("Renata",    "Flores",    "56912345626", "Tomás Flores",       "56912345666", date(1995, 10, 20)),
    ("Roxana",    "Torres",    "56912345627", "Nicolás Torres",     "56912345667", date(1983,  1,  9)),
    ("Yasna",     "Vodanovic", "56912345628", "Claudio Vodanovic",  "56912345668", date(1990,  6, 18)),
    ("Noelia",    "Antunovic", "56912345629", "Víctor Antunovic",   "56912345669", date(1988,  4,  3)),
    ("Angélica",  "Ramírez",   "56912345630", "Oscar Ramírez",      "56912345670", date(1993,  9, 27)),
    ("Susana",    "Casic",     "56912345631", "Hugo Casic",         "56912345671", date(1984,  2, 14)),
    ("Viviana",   "Zimunovic", "56912345632", "Esteban Zimunovic",  "56912345672", date(1991,  7,  6)),
    ("Alejandra", "Silva",     "56912345633", "Mauricio Silva",     "56912345673", date(1996, 11, 23)),
    ("Ximena",    "Vodanovic", "56912345634", "Patricio Vodanovic", "56912345674", date(1987,  5, 10)),
    ("Fabiola",   "Antunovic", "56912345635", "Antonio Antunovic",  "56912345675", date(1992,  8, 29)),
    ("Claudia",   "Medina",    "56912345636", "Ramón Medina",       "56912345676", date(1985,  3,  1)),
    ("Elena",     "Casic",     "56912345637", "Julio Casic",        "56912345677", date(1994, 10, 12)),
    ("Rosa",      "Zimunovic", "56912345638", "Miguel Zimunovic",   "56912345678", date(1989,  1, 31)),
    ("Alejandra", "Navarro",   "56912345639", "Alfredo Navarro",    "56912345679", date(1986,  6, 22)),
    ("Pilar",     "Vodanovic", "56912345640", "Sergio Vodanovic",   "56912345680", date(1993,  4,  5)),
]

DEFAULT_PASSWORD = "Pilates2026!"


class Command(BaseCommand):
    help = "Inserta las 40 usuarias de prueba con email generado por iniciales."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Muestra los emails que se crearían sin insertar nada.",
        )
        parser.add_argument(
            "--password",
            default=DEFAULT_PASSWORD,
            help=f"Contraseña para todas las usuarias (default: {DEFAULT_PASSWORD})",
        )

    def handle(self, *args, **options):
        dry_run  = options["dry_run"]
        password = options["password"]

        emails_usados: set = set(
            User.objects.values_list("email", flat=True)
        )
        creadas = 0
        omitidas = 0

        self.stdout.write(self.style.MIGRATE_HEADING(
            f"\n{'[DRY RUN] ' if dry_run else ''}Procesando {len(USUARIAS)} usuarias...\n"
        ))

        with transaction.atomic():
            for nombre, apellido, tel, cont_emerg, tel_emerg, fnac in USUARIAS:
                email = generar_email(nombre, apellido, emails_usados)

                # ── Verificar si ya existe ────────────────────────────
                if User.objects.filter(email=email).exists():
                    self.stdout.write(
                        f"  OMITIDA  {nombre} {apellido:<15} — {email} (ya existe)"
                    )
                    omitidas += 1
                    continue

                if dry_run:
                    self.stdout.write(
                        f"  [dry]    {nombre} {apellido:<15} → {email}"
                    )
                    emails_usados.add(email)
                    creadas += 1
                    continue

                # ── Crear User ────────────────────────────────────────
                # username = email (allauth usa email como login)
                user = User.objects.create_user(
                    username   = email,
                    email      = email,
                    password   = password,
                    first_name = nombre,
                    last_name  = apellido,
                )

                # ── Actualizar UserMetadata (creado por señal post_save) ──
                meta = UserMetadata.objects.get(user=user)
                meta.telefono             = tel
                meta.contacto_emergencia  = cont_emerg
                meta.telefono_emergencia  = tel_emerg
                meta.fecha_nacimiento     = fnac
                meta.save()

                emails_usados.add(email)
                creadas += 1

                self.stdout.write(
                    f"  ✓  {nombre} {apellido:<15} → {email}  (socio #{meta.numero_socio})"
                )

            if dry_run:
                # Revertir para que sea realmente un dry-run
                transaction.set_rollback(True)

        # ── Resumen ───────────────────────────────────────────────────
        self.stdout.write("")
        if dry_run:
            self.stdout.write(self.style.WARNING(
                f"[DRY RUN] Se habrían creado {creadas} usuarias. Nada fue guardado."
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"\n✅  {creadas} usuarias creadas | {omitidas} omitidas (ya existían)."
            ))
            self.stdout.write(
                f"    Contraseña de todas: {password}"
            )
