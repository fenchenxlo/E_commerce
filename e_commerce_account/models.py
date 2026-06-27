

# Create your models here.
from django.db import models  # 匯入 Django 模型系統
from django.contrib.auth.models import User  # 匯入 Django 內建 User 模型


class UserProfile(models.Model):  # 建立會員資料擴充模型
    user = models.OneToOneField(User, on_delete=models.CASCADE)  
    # 與 User 一對一關聯，刪除 User 時連帶刪除 Profile

    phone = models.CharField(max_length=20, blank=True)  
    # 手機號碼，可留空

    email = models.EmailField(null=True, blank=True)
    # E-Mail，可留空
    
    address = models.CharField(max_length=255, blank=True)  
    # 地址，可留空

    birthday = models.DateField(null=True, blank=True)  
    # 生日，可留空
    
    is_Vip = models.BooleanField(default=False, blank=True)
    # 是否為 VIP
    
    def __str__(self):
        return self.user.username  # 後台顯示使用者名稱