from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import datetime
from reservas.models import Sesion

class Command(BaseCommand):
    help = 'Libera cupos de recuperaciones no realizadas después de las 12pm'

    def handle(self, *args, **kwargs):
        ahora = timezone.now()
        liberadas = 0

        sesiones = Sesion.objects.filter(estado='RECUPERAR', marcada_ausente_en__isnull=False)

        for sesion in sesiones:
            dia_siguiente = sesion.marcada_ausente_en.date() + sesion.marcada_ausente_en.resolution
            plazo = timezone.make_aware(
                datetime.combine(dia_siguiente, datetime.min.time().replace(hour=12))
            )
            if ahora >= plazo:
                sesion.estado = 'AUSENTE'
                sesion.save()
                liberadas += 1

        self.stdout.write(self.style.SUCCESS(f'{liberadas} recuperaciones liberadas.'))
```

Y en el crontab de la VM (cuando hagas deploy) agregar:
```
0 12 * * * cd /ruta/proyecto && python manage.py liberar_recuperaciones
