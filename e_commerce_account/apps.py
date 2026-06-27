from django.apps import AppConfig


class E_Commerce_AccountConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'e_commerce_account'

    def ready(self):
        import e_commerce_account.signals