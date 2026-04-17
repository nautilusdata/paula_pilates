from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from reservas.models import Pack


class Command(BaseCommand):
    help = 'Elimina packs PENDIENTE_PAGO con más de 24 horas sin pagar'

    def handle(self, *args, **options):
        umbral = timezone.now() - timedelta(hours=24)

        packs_expirados = Pack.objects.filter(
            estado='PENDIENTE_PAGO',
            creado_en__lt=umbral,
        )

        total = packs_expirados.count()

        if total == 0:
            self.stdout.write('No hay packs expirados.')
            return

        packs_expirados.delete()
        self.stdout.write(
            self.style.SUCCESS(f'{total} pack(s) expirado(s) eliminado(s).')
        )