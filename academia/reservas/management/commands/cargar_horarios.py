from django.core.management.base import BaseCommand
from reservas.models import ConfiguracionHorario

class Command(BaseCommand):
    help = 'Carga horarios iniciales en la DB'

    def handle(self, *args, **kwargs):
        ConfiguracionHorario.objects.all().delete()

        # PL — Pilates Grupal
        # Lun-Jue: 8,9,10,17,18,19 / Vie: 8,9,10,18,19
        pl = [
            (0, [8,9,10,17,18,19]),  # Lunes
            (1, [8,9,10,17,18,19]),  # Martes
            (2, [8,9,10,17,18,19]),  # Miércoles
            (3, [8,9,10,17,18,19]),  # Jueves
            (4, [8,9,10,18,19]),     # Viernes
        ]
        for dia, horas in pl:
            for hora in horas:
                ConfiguracionHorario.objects.create(dia=dia, hora=hora, tipo='PL')

        # PV — Pilates Privada
        # Lun-Vie: 11, 16
        for dia in range(5):
            for hora in [11, 16]:
                ConfiguracionHorario.objects.create(dia=dia, hora=hora, tipo='PV')

        # BDB — Body Balance
        ConfiguracionHorario.objects.create(dia=1, hora=20, tipo='BDB')  # Martes
        ConfiguracionHorario.objects.create(dia=3, hora=20, tipo='BDB')  # Jueves
        ConfiguracionHorario.objects.create(dia=5, hora=11, tipo='BDB')  # Sábado

        # TEST — Clase de Prueba
        ConfiguracionHorario.objects.create(dia=5, hora=12, tipo='TEST')  # Sábado

        self.stdout.write(self.style.SUCCESS(
            f'Horarios cargados: {ConfiguracionHorario.objects.count()} slots'
        ))

        # Configuración general
        from reservas.models import ConfiguracionGeneral
        ConfiguracionGeneral.objects.get_or_create(
        clave='CAPACIDAD_REFORMERS',
        defaults={'valor': 7, 'descripcion': 'Número de reformers disponibles'}
        )
        ConfiguracionGeneral.objects.get_or_create(
        clave='CAPACIDAD_BODY_BALANCE',
        defaults={'valor': 20, 'descripcion': 'Capacidad máxima sala Body Balance'}
        )
        self.stdout.write(self.style.SUCCESS('Configuración general cargada.'))