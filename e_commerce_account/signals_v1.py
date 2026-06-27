from allauth.account.signals import user_signed_up
from django.db.models.signals import post_save  # 匯入 post_save 訊號（模型儲存後觸發）
from django.dispatch import receiver  # 註冊訊號接收器
from django.contrib.auth.models import User  # 匯入 User 模型
from .models import UserProfile  # 匯入 UserProfile 模型

from allauth.account.models import EmailAddress
from e_commerce_account.adapters import MyAccountAdapter

@receiver(post_save, sender=User)  # 當 User 被建立或更新時觸發
def create_profile(sender, instance, created, **kwargs):

    if created:  # 只有在 User 第一次建立時執行
        # 假設 user 剛註冊
        user_email = EmailAddress.objects.get(user=user, email=user.email)

        UserProfile.objects.create(user=user, email=user_email.email, is_Vip=False)  
        # 自動建立對應的 UserProfile
        print(f"Profile created for {user.email}")
        

#         adapter = MyAccountAdapter()
#         # signup=True 只是告訴 Adapter 這是註冊流程
#         adapter.send_confirmation_mail(request, user_email, signup=True)
