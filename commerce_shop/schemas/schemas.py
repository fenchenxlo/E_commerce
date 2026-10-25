from dataclasses import dataclass
from django.contrib.auth.models import User


@dataclass
class CheckoutSchema:

    user: User