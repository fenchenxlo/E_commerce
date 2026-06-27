from django.contrib import admin
from .models import UserProfile  # 匯入 UserProfile 模型
# Register your models here.

@admin.register(UserProfile)  # 註冊 UserProfile 模型到 Django admin
class UserProfileAdmin(admin.ModelAdmin):  # 自訂 Product 在後台的顯示方式
    list_display = ('user', 'phone', 'email', 'address', 'birthday', 'is_Vip')  # 後台列表要顯示的欄位

    search_fields = ('user__name', 'user__email', 'phone', 'address')  # 可搜尋的欄位

    list_filter = ('is_Vip',)  # 篩選器（依價格篩選）<==這裏要是list or tuple


