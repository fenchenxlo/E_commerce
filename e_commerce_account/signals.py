from allauth.account.signals import user_signed_up
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import UserProfile
from allauth.account.models import EmailAddress

@receiver(user_signed_up)
def create_profile(request, user, **kwargs):
    """
    當使用者註冊時：
    1. 確保 EmailAddress 寫入 DB
    2. 建立 UserProfile
    """
    # 確保 EmailAddress 存在
    email_address, created = EmailAddress.objects.get_or_create(
        user=user,
        email=user.email,
        defaults={"verified": False, "primary": True}
    )

    if created:
        print(f"EmailAddress created for {user.email}")
    else:
        print(f"EmailAddress already exists for {user.email}")

    # 建立 UserProfile
    user_profile, created = UserProfile.objects.get_or_create(
        user=user,
        defaults={
            "is_Vip": False,
            "email": user.email  # 把 email 寫入 UserProfile
        }
    )

    if created:
        print(f"UserProfile created for {user.email}")
    else:
        print(f"UserProfile already exists for {user.email}")
