from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.exceptions import ValidationError
from django.db import transaction
from datetime import date, timedelta
import holidays
import os
import requests as http_requests
import logging

logger = logging.getLogger(__name__)


# ─── Helpers de fecha ────────────────────────────────────────────────────────

def feriados_punta_arenas(years=None):
    """Feriados Chile, región Magallanes (incluye 21 sep)."""
    if years is None:
        hoy = date.today()
        years = list(range(hoy.year, hoy.year + 3))
    return holidays.Chile(subdiv='MA', years=years)


def generar_fechas_pack(fecha_inicio: date, dias: list,
                        horas: dict, cantidad: int = 10):
    """
    Genera lista de (fecha, hora) para el pack.

    dias  = lista de weekdays elegidos, ej: [0, 2, 5] (Lun, Mié, Sáb)
    horas = dict {dia_semana: hora}, ej: {0: 9, 2: 10, 5: 11}

    Salta feriados de Punta Arenas.
    El primer día DEBE coincidir con uno de los días elegidos.
    """
    feriados = feriados_punta_arenas()

    if fecha_inicio.weekday() not in dias:
        raise ValidationError(
            "La fecha de inicio no corresponde a un día válido para la frecuencia elegida."
        )

    if fecha_inicio in feriados:
        raise ValidationError(
            "La fecha de inicio es un feriado. Por favor elige otro día."
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
    Usa pack.frecuencia como string de días separados por coma, ej: '0,2,5'
    """
    if not pack.frecuencia:
        return {}
    dias = [int(d) for d in pack.frecuencia.split(',')]
    horas = {}
    campos = [pack.hora_dia1, pack.hora_dia2, pack.hora_dia3, pack.hora_dia4]
    for i, dia in enumerate(dias):
        if i < len(campos) and campos[i] is not None:
            horas[dia] = campos[i]
    return horas


def dias_para_pack(pack) -> list:
    """Retorna lista de weekdays del pack, ej: [0, 2, 5]"""
    if not pack.frecuencia:
        return []
    return [int(d) for d in pack.frecuencia.split(',')]


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
        # Notificar al developer
        try:
            token       = os.getenv('TELEGRAM_BOT_TOKEN')
            chat_id_dev = os.getenv('TELEGRAM_USER_ID')
            if token and chat_id_dev:
                nombre = instance.get_full_name() or instance.username
                mensaje = "\U0001f464 *Nueva alumna registrada*\n" + nombre + "\n\U0001f4e7 " + instance.email
                http_requests.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={
                        "chat_id":    chat_id_dev,
                        "text":       mensaje,
                        "parse_mode": "Markdown",
                    },
                    timeout=5,
                )
        except Exception as e:
            logger.error("Telegram nueva alumna excepción: %s", e)


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

    ESTADO_CHOICES = [
        ('PENDIENTE_PAGO', 'Pendiente de pago'),
        ('ACTIVO',         'Activo'),
        ('COMPLETADO',     'Completado'),
        ('CONGELADO',      'Congelado'),
        ('CANCELADO',      'Cancelado'),
    ]

    alumna     = models.ForeignKey(User, on_delete=models.CASCADE, related_name='packs')
    tipo       = models.CharField(max_length=20, choices=TIPO_CHOICES)

    # Días elegidos como string separado por comas, ej: '0,2,5' (Lun,Mié,Sáb)
    frecuencia = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        help_text='Días elegidos, ej: 0,2,5 (Lun,Mié,Sáb)'
    )

    # Hora por día — dia1=primer día elegido, dia2=segundo, etc.
    hora_dia1 = models.PositiveSmallIntegerField(null=True, blank=True, help_text='Hora día 1')
    hora_dia2 = models.PositiveSmallIntegerField(null=True, blank=True, help_text='Hora día 2')
    hora_dia3 = models.PositiveSmallIntegerField(null=True, blank=True, help_text='Hora día 3')
    hora_dia4 = models.PositiveSmallIntegerField(null=True, blank=True, help_text='Hora día 4')

    # Para productos de una sola hora (SUELTA, PRUEBA, BB, PRIVADA)
    hora = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text='Hora única (para productos no-pack)'
    )

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
        # Validación simplificada — solo verifica horas contra slots activos PL
        if self.tipo in ('PACK10', 'REDUCIDO') and self.frecuencia:
            dias = dias_para_pack(self)
            horas_validas = horas_disponibles_por_tipo('PL')
            campos = [self.hora_dia1, self.hora_dia2, self.hora_dia3, self.hora_dia4]
            for i, dia in enumerate(dias):
                if i < len(campos) and campos[i] is not None:
                    horas_dia = horas_disponibles_por_tipo('PL', dia=dia)
                    if campos[i] not in horas_dia:
                        raise ValidationError(
                            f'Hora {campos[i]} no válida para Pilates el día {dia}.'
                        )

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
        ordering        = ['fecha', 'hora']
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
    if pack.tipo not in ('PACK10', 'REDUCIDO', 'PRIVADA'):
        raise ValueError('Solo packs tienen sesiones múltiples con esta función.')

    # PRIVADA usa una sola hora para todos los días
    if pack.tipo == 'PRIVADA':
        dias = dias_para_pack(pack)
        horas = {d: pack.hora for d in dias}
    else:
        horas = horas_para_pack(pack)
        dias  = dias_para_pack(pack)

    pares = generar_fechas_pack(pack.fecha_inicio, dias, horas, pack.cantidad)

    with transaction.atomic():
        Sesion.objects.select_for_update().filter(
            fecha__in=[f for f, h in pares],
            hora__in=list(set(h for f, h in pares)),
        )

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


def detectar_overlap(alumna, pares: list) -> list:
    """
    Verifica si la alumna ya tiene sesiones activas que colisionen
    con alguna de las (fecha, hora) del nuevo pack.
    """
    colisiones = []
    for f, h in pares:
        ya_tiene = Sesion.objects.filter(
            pack__alumna=alumna,
            pack__estado__in=['ACTIVO', 'PENDIENTE_PAGO'],
            fecha=f,
            hora=h,
            estado__in=['PROGRAMADA', 'RECUPERAR'],
        ).exists()
        if ya_tiene:
            colisiones.append((f, h))
    return colisiones


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


def slots_disponibles_pl() -> dict:
    """
    Retorna dict {dia: [hora, hora, ...]} con todos los slots PL activos.
    Útil para el flujo de reserva libre.
    """
    qs = ConfiguracionHorario.objects.filter(tipo='PL', activo=True).order_by('dia', 'hora')
    resultado = {}
    for ch in qs:
        resultado.setdefault(ch.dia, []).append(ch.hora)
    return resultado


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