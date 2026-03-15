from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.exceptions import ValidationError
from datetime import date, timedelta
import holidays



# ─── Constantes de Negocio ────────────────────────────────────────────────────

DIAS_SEMANA_PILATES = {
    'LMV': [0, 2, 4],   # Lunes, Miércoles, Viernes
    'LM':  [0, 2],       # Lunes, Miércoles
    'MJ':  [1, 3],       # Martes, Jueves
}

HORAS_PILATES = [8, 9, 10, 11, 17, 18, 19]   # horas disponibles en reformers

CAPACIDAD_REFORMERS = 6





class UserMetadata(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    numero_socio = models.CharField(max_length=10, unique=True, blank=True)
    telefono = models.CharField(max_length=20, blank=True)
    contacto_emergencia = models.CharField(max_length=100, blank=True)
    telefono_emergencia = models.CharField(max_length=20, blank=True)
    fecha_nacimiento = models.DateField(null=True, blank=True)

    def __str__(self):
        return f"{self.numero_socio} - {self.user.get_full_name()}"

@receiver(post_save, sender=User)
def crear_metadata(sender, instance, created, **kwargs):
    if created:
        ultimo = UserMetadata.objects.order_by('-id').first()
        numero = (ultimo.id + 1) if ultimo else 1
        UserMetadata.objects.create(
            user=instance,
            numero_socio=f"{numero:03d}"
        )
'''Es un signal — Django tiene un sistema de señales que permite ejecutar código automáticamente cuando ocurre algo en el sistema.
@receiver(post_save, sender=User) significa: "cada vez que se guarde un objeto User, ejecuta esta función". El parámetro created distingue si es un User nuevo o una edición de uno existente, por eso el if created: — solo crea el UserMetadata cuando el User es nuevo, no cada vez que se edita.
Es como un gancho automático: se registra una nueva alumna → Django guarda el User → el signal se dispara → se crea el UserMetadata con su número de socia asignado automáticamente. Todo sin que tengas que acordarte de hacerlo manualmente.

Para acceder a los datos desde cualquier parte del código es muy simple:
# Desde el User llegas al UserMetadata
request.user.usermetadata.telefono
request.user.usermetadata.numero_socio

# Desde el UserMetadata llegas al User
metadata.user.first_name
metadata.user.email.Django maneja esa navegación en ambas direcciones automáticamente gracias al OneToOneField.
'''

def feriados_punta_arenas(years=None):
    """Feriados Chile, región Magallanes (incluye 21 sep)."""
    if years is None:
        hoy = date.today()
        years = list(range(hoy.year, hoy.year + 3))
    return holidays.Chile(subdiv='MA', years=years)


def generar_fechas_pack(fecha_inicio: date, frecuencia: str, cantidad: int = 10):
    """
    Genera lista de `cantidad` fechas para el pack, partiendo en `fecha_inicio`,
    con la frecuencia indicada ('LMV', 'LM', 'MJ'), saltando feriados.
    El primer día DEBE coincidir con uno de los días de la frecuencia elegida.
    """
    dias = DIAS_SEMANA_PILATES[frecuencia]
    feriados = feriados_punta_arenas()

    if fecha_inicio.weekday() not in dias:
        raise ValidationError(
            "La fecha de inicio no corresponde a un día válido para la frecuencia elegida."
        )

    fechas = []
    cursor = fecha_inicio

    while len(fechas) < cantidad:
        if cursor.weekday() in dias and cursor not in feriados:
            fechas.append(cursor)
        cursor += timedelta(days=1)

    return fechas


# ─── Modelos ──────────────────────────────────────────────────────────────────

class Pack(models.Model):
    """
    Representa la compra de un pack por parte de una alumna.
    Contiene la configuración general; las sesiones individuales
    se crean en Sesion.
    """
    TIPO_CHOICES = [
        ('PACK10',    'Pack 10 Clases'),
        ('REDUCIDO',  'Pack Reducido (2–9 clases)'),
        ('SUELTA',    'Clase Suelta'),
        ('PRUEBA',    'Clase de Prueba'),
        ('PRIVADA',   'Clase Privada'),
    ]

    FRECUENCIA_CHOICES = [
        ('LMV', 'Lunes – Miércoles – Viernes'),
        ('LM',  'Lunes – Miércoles'),
        ('MJ',  'Martes – Jueves'),
    ]

    ESTADO_CHOICES = [
        ('PENDIENTE_PAGO', 'Pendiente de pago'),
        ('ACTIVO',         'Activo'),
        ('COMPLETADO',     'Completado'),
        ('CONGELADO',      'Congelado'),
        ('CANCELADO',      'Cancelado'),
    ]

    alumna        = models.ForeignKey(User, on_delete=models.CASCADE, related_name='packs')
    tipo          = models.CharField(max_length=20, choices=TIPO_CHOICES)
    frecuencia    = models.CharField(max_length=3, choices=FRECUENCIA_CHOICES, blank=True)
    hora          = models.PositiveSmallIntegerField(help_text='Hora de inicio (8, 9, 10…)')
    fecha_inicio  = models.DateField()
    fecha_fin     = models.DateField(blank=True, null=True)   # calculada al crear
    cantidad      = models.PositiveSmallIntegerField(default=10)
    precio_total  = models.PositiveIntegerField(editable=False)
    estado        = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='PENDIENTE_PAGO')
    creado_en     = models.DateTimeField(auto_now_add=True)

    def calcular_precio(self):
        precios = {
            'PACK10':   140_000,
            'SUELTA':    25_000,
            'PRUEBA':    15_000,
        }
        if self.tipo == 'PACK10':
            return 140_000
        if self.tipo == 'REDUCIDO':
            if not (2 <= self.cantidad <= 9):
                raise ValidationError('Pack reducido debe tener entre 2 y 9 clases.')
            return self.cantidad * 20_000
        return precios.get(self.tipo, 0)

    def clean(self):
        if self.tipo in ('PACK10', 'REDUCIDO') and self.hora not in HORAS_PILATES:
            raise ValidationError(f'Hora {self.hora} no es válida para Pilates Reformer.')

    def save(self, *args, **kwargs):
        self.full_clean()
        self.precio_total = self.calcular_precio()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.alumna.get_full_name()} | {self.get_tipo_display()} | {self.fecha_inicio}"


class Sesion(models.Model):
    """
    Una clase individual dentro de un pack.
    Se crean en bloque cuando el pack se confirma (pago exitoso).
    """
    ESTADO_CHOICES = [
        ('PROGRAMADA',  'Programada'),
        ('COMPLETADA',  'Completada'),
        ('AUSENTE',     'Ausente sin aviso'),
        ('RECUPERAR',   'Pendiente recuperación'),
        ('RECUPERADA',  'Recuperada'),
        ('CONGELADA',   'Congelada'),
        ('CANCELADA',   'Cancelada por el centro'),
    ]

    pack         = models.ForeignKey(Pack, on_delete=models.CASCADE, related_name='sesiones')
    fecha        = models.DateField()
    hora         = models.PositiveSmallIntegerField()
    numero       = models.PositiveSmallIntegerField(help_text='Clase nº dentro del pack (1 a 10)')
    estado       = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='PROGRAMADA')
    es_recupero  = models.BooleanField(default=False)
    sesion_orig  = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='recuperaciones', help_text='Sesión original que se recupera'
    )

    class Meta:
        ordering = ['fecha', 'hora']
        unique_together = [('fecha', 'hora', 'pack')]

    @classmethod
    def cupos_disponibles(cls, fecha: date, hora: int) -> int:
        """Retorna cupos libres en un slot dado (máx CAPACIDAD_REFORMERS)."""
        ocupados = cls.objects.filter(
            fecha=fecha,
            hora=hora,
            estado__in=['PROGRAMADA', 'RECUPERAR', 'RECUPERADA'],
        ).count()
        return CAPACIDAD_REFORMERS - ocupados

    def __str__(self):
        return f"#{self.numero} {self.fecha} {self.hora}:00 — {self.pack.alumna.get_full_name()}"


# ─── Helper: crear sesiones al confirmar pago ─────────────────────────────────

def crear_sesiones_pack(pack: Pack):
    """
    Genera las Sesion del pack después de confirmación de pago.
    Valida disponibilidad de cupos antes de crear.
    """
    if pack.tipo not in ('PACK10', 'REDUCIDO'):
        raise ValueError('Solo packs tienen sesiones múltiples con esta función.')

    fechas = generar_fechas_pack(pack.fecha_inicio, pack.frecuencia, pack.cantidad)

    # Verificar disponibilidad en cada fecha
    sin_cupo = [f for f in fechas if Sesion.cupos_disponibles(f, pack.hora) < 1]
    if sin_cupo:
        raise ValidationError(
            f'Sin cupo disponible en: {", ".join(str(f) for f in sin_cupo)}'
        )

    sesiones = [
        Sesion(pack=pack, fecha=f, hora=pack.hora, numero=i + 1)
        for i, f in enumerate(fechas)
    ]
    Sesion.objects.bulk_create(sesiones)

    pack.fecha_fin = fechas[-1]
    pack.estado = 'ACTIVO'
    pack.save(update_fields=['fecha_fin', 'estado'])

    return sesiones