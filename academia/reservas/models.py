from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

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