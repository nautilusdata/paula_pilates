from allauth.account.adapter import DefaultAccountAdapter
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

class WhitelistEmailAdapter(DefaultAccountAdapter):
    def clean_email(self, email):
        email = super().clean_email(email)
        if not User.objects.filter(email=email).exists():
            raise ValidationError(
                'Este email no está registrado en nuestro sistema. '
                'Contacta a la Academia para inscribirte.'
            )
        return email
