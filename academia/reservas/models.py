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


# ─── Helpers de fecha ────────────────────────────────────────────────────────

def feriados_punta_arenas(years=None):
    """Feriados Chile, región Magallanes (incluye 21 sep)."""
    if years is None:
        hoy = date.today()
        years = list(range(hoy.year, hoy.year + 3))
    return holidays.Chile(subdiv='MA', years=years)


def generar_fechas_pack(fecha_inicio: date, frecuencia: str,
                         horas: dict, cantidad: int = 10):
    """
    Genera lista de (fecha, hora) para el pack.

    horas = dict {dia_semana: hora}
    Ejemplos:
      LMV → {0: 9, 2: 10, 4: 8}   Lunes 9am, Mié 10am, Vie 8am
      LM  → {0: 9, 2: 10}
      MJ  → {1: 9, 3: 10}

    Salta feriados de Punta Arenas.
    El primer día DEBE coincidir con uno de los días de la frecuencia.
    """
    dias = DIAS_SEMANA_PILATES[frecuencia]
    feriados = feriados_punta_arenas()

    if fecha_inicio.weekday() not in dias:
        raise ValidationError(
            "La fecha de inicio no corresponde a un día válido para la frecuencia elegida."
        )

    resultado = []
    cursor = fecha_inicio

    while len(resultado) < cantidad:
        if cursor.weekday() in dias and cursor not in feriados:
            hora = horas[cursor.weekday()]
            resultado.append((cursor, hora))
        cursor += timedelta(days=1)

    return resultado  # list of (date, hora)


def horas_para_pack(pack) -> dict:
    """
    Construye el dict {dia_semana: hora} a partir de los campos hora_dia* del pack.
    """
    dias = DIAS_SEMANA_PILATES[pack.frecuencia]
    horas = {
        dias[0]: pack.hora_dia1,
        dias[1]: pack.hora_dia2,
    }
    if len(dias) == 3 and pack.hora_dia3 is not None:
        horas[dias[2]] = pack.hora_dia3
    return horas


# --------------------- Modelos ───────────────────────────────────────────────

class UserMetadata(models.Model):
    user                 = models.OneToOneField(User, on_delete=models.CASCADE)
    numero_socio         = models.CharField(max_length=10, unique=True, blank=True)
    telefono             = models.CharField(max_length=20, blank=True)
    contacto_emergencia  = models.CharField(max_length=100, blank=True)
    telefono_emergencia  = models.CharField(max_length=20, blank=True)
    fecha_nacimiento     = models.DateField(null=True, blank=True)

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


class Pack(models.Model):
    TIPO_CHOICES = [
        ('PACK10',     'Pack 10 Clases'),
        ('REDUCIDO',   'Pack Reducido (2–9 clases)'),
        ('SUELTA',     'Clase Suelta'),
        ('PRUEBA',     'Clase de Prueba'),
        ('PRIVADA',    'Clase Privada'),
        ('BB_FULL',    'Body Balance Mensualidad'),
        ('BB_SEMANAL', 'Body Balance Clase Semanal'),
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

    alumna       = models.ForeignKey(User, on_delete=models.CASCADE, related_name='packs')
    tipo         = models.CharField(max_length=20, choices=TIPO_CHOICES)
    frecuencia   = models.CharField(max_length=3, choices=FRECUENCIA_CHOICES, blank=True)

    # Hora por día de frecuencia (reemplaza el campo único 'hora')
    # dia1 = primer día de la frecuencia (Lun o Mar)
    # dia2 = segundo día (Mié o Jue)
    # dia3 = tercer día (Vie) — solo para LMV
    hora_dia1    = models.PositiveSmallIntegerField(
                       null=True, blank=True,
                       help_text='Hora día 1 (Lun o Mar)')
    hora_dia2    = models.PositiveSmallIntegerField(
                       null=True, blank=True,
                       help_text='Hora día 2 (Mié o Jue)')
    hora_dia3    = models.PositiveSmallIntegerField(
                       null=True, blank=True,
                       help_text='Hora día 3 (Vie) — solo LMV')

    # Para productos de una sola hora (SUELTA, PRUEBA, BB, PRIVADA)
    hora         = models.PositiveSmallIntegerField(
                       null=True, blank=True,
                       help_text='Hora única (para productos no-pack)')

    fecha_inicio = models.DateField()
    fecha_fin    = models.DateField(blank=True, null=True)
    cantidad     = models.PositiveSmallIntegerField(default=10)
    precio_total = models.PositiveIntegerField(editable=False)
    estado       = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='PENDIENTE_PAGO')
    creado_en    = models.DateTimeField(auto_now_add=True)

    def calcular_precio(self):
        if self.tipo == 'PACK10':
            return ConfiguracionPrecio.get('PACK10', 140_000)
        if self.tipo == 'REDUCIDO':
            if not (2 <= self.cantidad <= 9):
                raise ValidationError('Pack reducido debe tener entre 2 y 9 clases.')
            return self.cantidad * ConfiguracionPrecio.get('PACK_REDUCIDO_CLASE', 20_000)
        if self.tipo == 'SUELTA':
            return ConfiguracionPrecio.get('CLASE_SUELTA', 25_000)
        if self.tipo == 'PRUEBA':
            return ConfiguracionPrecio.get('CLASE_PRUEBA', 15_000)
        if self.tipo == 'PRIVADA':
            return ConfiguracionPrecio.get('PRIVADA_PACK10', 285_000)
        if self.tipo == 'BB_FULL':
            return ConfiguracionPrecio.get('BB_FULL', 60_000)
        if self.tipo == 'BB_SEMANAL':
            return ConfiguracionPrecio.get('BB_SEMANAL', 15_000)
        return 0

    def clean(self):
        horas_validas = horas_disponibles_por_tipo('PL')
        if self.tipo in ('PACK10', 'REDUCIDO'):
            for campo, label in [
                (self.hora_dia1, 'hora día 1'),
                (self.hora_dia2, 'hora día 2'),
            ]:
                if campo is not None and campo not in horas_validas:
                    raise ValidationError(f'{label} {campo} no es válida para Pilates.')
            if self.frecuencia == 'LMV' and self.hora_dia3 is not None:
                if self.hora_dia3 not in horas_disponibles_por_tipo('PL', dia=4):
                    raise ValidationError(f'hora día 3 (Vie) {self.hora_dia3} no es válida.')

    def save(self, *args, **kwargs):
        self.full_clean()
        self.precio_total = self.calcular_precio()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.alumna.get_full_name()} | {self.get_tipo_display()} | {self.fecha_inicio}"


class Sesion(models.Model):
    ESTADO_CHOICES = [
        ('PROGRAMADA', 'Programada'),
        ('COMPLETADA', 'Completada'),
        ('AUSENTE',    'Ausente sin aviso'),
        ('RECUPERAR',  'Pendiente recuperación'),
        ('RECUPERADA', 'Recuperada'),
        ('CONGELADA',  'Congelada'),
        ('CANCELADA',  'Cancelada por el centro'),
    ]

    pack               = models.ForeignKey(Pack, on_delete=models.CASCADE, related_name='sesiones')
    fecha              = models.DateField()
    hora               = models.PositiveSmallIntegerField()
    numero             = models.PositiveSmallIntegerField(help_text='Clase nº dentro del pack')
    estado             = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='PROGRAMADA')
    es_recupero        = models.BooleanField(default=False)
    sesion_orig        = models.ForeignKey(
                             'self', null=True, blank=True, on_delete=models.SET_NULL,
                             related_name='recuperaciones')
    marcada_ausente_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering       = ['fecha', 'hora']
        unique_together = [('fecha', 'hora', 'pack')]

    @classmethod
    def cupos_disponibles(cls, fecha: date, hora: int) -> int:
        ocupados = cls.objects.filter(
            fecha=fecha,
            hora=hora,
            estado__in=['PROGRAMADA', 'RECUPERAR', 'RECUPERADA'],
        ).count()
        return ConfiguracionGeneral.get('CAPACIDAD_REFORMERS', 6) - ocupados

    def __str__(self):
        return f"#{self.numero} {self.fecha} {self.hora}:00 — {self.pack.alumna.get_full_name()}"


# ─── Helper: crear sesiones al confirmar pago ─────────────────────────────────

def crear_sesiones_pack(pack: Pack):
    """
    Genera las Sesion del pack después de confirmación de pago.
    Cada fecha tiene su hora específica según el día de la semana.
    """
    if pack.tipo not in ('PACK10', 'REDUCIDO', 'PRIVADA'):
        raise ValueError('Solo packs tienen sesiones múltiples con esta función.')

    horas = horas_para_pack(pack)
    pares = generar_fechas_pack(pack.fecha_inicio, pack.frecuencia, horas, pack.cantidad)

    # Verificar disponibilidad en cada slot
    sin_cupo = [(f, h) for f, h in pares if Sesion.cupos_disponibles(f, h) < 1]
    if sin_cupo:
        fechas_str = ', '.join(str(f) for f, _ in sin_cupo)
        raise ValidationError(f'Sin cupo disponible en: {fechas_str}')

    sesiones = [
        Sesion(pack=pack, fecha=f, hora=h, numero=i + 1)
        for i, (f, h) in enumerate(pares)
    ]
    Sesion.objects.bulk_create(sesiones)

    pack.fecha_fin = pares[-1][0]
    pack.estado    = 'ACTIVO'
    pack.save(update_fields=['fecha_fin', 'estado'])

    return sesiones


# ─── Panel de instructor ──────────────────────────────────────────────────────

class ConfiguracionGeneral(models.Model):
    clave       = models.CharField(max_length=50, unique=True)
    valor       = models.PositiveIntegerField()
    descripcion = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return f"{self.clave} = {self.valor}"

    @classmethod
    def get(cls, clave: str, default: int = 0) -> int:
        try:
            return cls.objects.get(clave=clave).valor
        except cls.DoesNotExist:
            return default


class ConfiguracionHorario(models.Model):
    TIPO_CHOICES = [
        ('PL',   'Pilates Grupal'),
        ('PV',   'Pilates Privada'),
        ('BDB',  'Body Balance'),
        ('TEST', 'Clase de Prueba'),
    ]

    DIA_CHOICES = [
        (0, 'Lunes'),
        (1, 'Martes'),
        (2, 'Miércoles'),
        (3, 'Jueves'),
        (4, 'Viernes'),
        (5, 'Sábado'),
    ]

    dia    = models.PositiveSmallIntegerField(choices=DIA_CHOICES)
    hora   = models.PositiveSmallIntegerField()
    tipo   = models.CharField(max_length=4, choices=TIPO_CHOICES)
    activo = models.BooleanField(default=True)

    class Meta:
        unique_together = [('dia', 'hora', 'tipo')]
        ordering        = ['hora', 'dia']

    def __str__(self):
        return f"{self.get_dia_display()} {self.hora:02d}:00 — {self.tipo}"


def horas_disponibles_por_tipo(tipo: str, dia: int = None) -> list:
    """
    Lee de la DB los horarios activos para un tipo dado.
    Si se pasa dia (0=Lun ... 5=Sáb), filtra por día también.
    """
    qs = ConfiguracionHorario.objects.filter(tipo=tipo, activo=True)
    if dia is not None:
        qs = qs.filter(dia=dia)
    return sorted(set(qs.values_list('hora', flat=True)))


class ConfiguracionPrecio(models.Model):
    clave       = models.CharField(max_length=50, unique=True)
    valor       = models.PositiveIntegerField()
    descripcion = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return f"{self.clave} = ${self.valor:,}"

    @classmethod
    def get(cls, clave: str, default: int = 0) -> int:
        try:
            return cls.objects.get(clave=clave).valor
        except cls.DoesNotExist:
            return default