from allauth.account.signals import user_signed_up
from django.db.models.signals import post_save  # 匯入 post_save 訊號（模型儲存後觸發）
from django.dispatch import receiver  # 註冊訊號接收器
from django.contrib.auth.models import User  # 匯入 User 模型
from .models import UserProfile  # 匯入 UserProfile 模型
from allauth.account.models import EmailAddress

@receiver(user_signed_up)
def create_profile(request, user, **kwargs):
    """
    當使用者註冊時：
    1. 確保 EmailAddress 已建立
    2. 建立 Profile
    3. 印出確認 email 到 console (解碼 base64)
    """
    try:
        email_address = EmailAddress.objects.get(user=user, email=user.email)
    except EmailAddress.DoesNotExist:
        print(f"[Warning] EmailAddress for {user.email} does not exist yet.")
        return

    user_profile, created = UserProfile.objects.get_or_create(
        user=user,
        defaults={"is_Vip": False}  # 這裡填你 UserProfile 的欄位預設值
    )

    if created:
        print(f"UserProfile created for {user.email}")
    else:
        print(f"UserProfile already exists for {user.email}")
