from django.db import models  # 從 Django 的 db 模組匯入 models，用來定義資料庫模型

# Create your models here.
from django.contrib.auth.models import User  # 匯入內建的 User 模型，代表系統使用者

class Product(models.Model):
    # Product：商品模型，儲存商品的基本資訊（名稱、描述、價格、庫存）

    name = models.CharField(max_length=100)  # 商品名稱，使用 CharField，最大長度 100 字元
    description = models.TextField(blank=True)  # 商品描述，TextField 可存放長文字，blank=True 代表可留空
    price = models.DecimalField(max_digits=10, decimal_places=2)  # 商品價格，DecimalField 用於金額，最多 10 位數，其中 2 位小數
    stock = models.PositiveIntegerField()  # 商品庫存數量，只允許正整數（含 0）

    def __str__(self):
        # 定義物件轉為字串時的顯示方式，這裡回傳商品名稱
        return self.name

class Cart(models.Model):
    # Cart：購物車模型，每個使用者對應一個購物車

    user = models.OneToOneField(
        User,  # 關聯到 Django 內建的 User 模型
        on_delete=models.CASCADE  # 當使用者被刪除時，連帶刪除其購物車
    )

class CartItem(models.Model):
    # CartItem：購物車項目模型，代表購物車中的一筆商品紀錄

    cart = models.ForeignKey(
        Cart,  # 關聯到 Cart 模型，一個購物車可以有多個 CartItem
        on_delete=models.CASCADE,  # 當購物車被刪除時，連帶刪除其所有 CartItem
        related_name='items'  # 讓 cart.items 可以反向取得該購物車的所有 CartItem
    )
    product = models.ForeignKey(
        Product,  # 關聯到 Product 模型，代表此項目對應的商品
        on_delete=models.CASCADE  # 當商品被刪除時，連帶刪除此 CartItem
    )
    quantity = models.PositiveIntegerField()  # 購買數量，只允許正整數（含 0 不含負數）
    price = models.DecimalField(
        max_digits=10,  # 總共最多 10 位數
        decimal_places=2  # 小數點後 2 位，適合金額
    )  # 商品價格快照：下單當下的商品價格，避免商品後續調價影響購物車紀錄

class Order(models.Model):
    # Order：訂單模型，紀錄使用者的訂單資訊（總金額、狀態、建立時間等）

    STATUS_CHOICES = [  # 訂單狀態可選項目, 前面 是實際存入資料庫的值, 後面是 會在應用程式或是管理介面中顯示
        ('pending', 'Pending'),  # pending：待付款或待處理
        ('paid', 'Paid'),  # paid：已付款
        ('shipped', 'Shipped'),  # shipped：已出貨
        ('cancelled', 'Cancelled'),  # cancelled：已取消
    ]
    
    user = models.ForeignKey(
        User,  # 關聯到 User 模型，代表此訂單屬於哪位使用者
        on_delete=models.CASCADE  # 當使用者被刪除時，連帶刪除其所有訂單
    )
    total_amount = models.DecimalField(
        max_digits=10,  # 總金額最多 10 位數
        decimal_places=2  # 小數點後 2 位
    )  # 訂單總金額，通常由所有 OrderItem 的小計加總而來
    status = models.CharField(
        max_length=10,  # 狀態字串最大長度 10
        choices=STATUS_CHOICES,  # 限制只能是 STATUS_CHOICES 中的其中一個值
        default='pending'  # 預設狀態為 pending（待處理）
    )
    created_at = models.DateTimeField(
        auto_now_add=True  # 在建立訂單時自動填入當下時間，只在第一次建立時設定
    )  # 訂單建立時間

class OrderItem(models.Model):
    # OrderItem：訂單項目模型，代表訂單中的一筆商品紀錄

    order = models.ForeignKey(
        Order,  # 關聯到 Order 模型，一個訂單可以有多個 OrderItem
        on_delete=models.CASCADE,  # 當訂單被刪除時，連帶刪除其所有 OrderItem
        related_name='items'  # 讓 order.items 可以反向取得該訂單的所有 OrderItem
    )
    product = models.ForeignKey(
        Product,  # 關聯到 Product 模型，代表此訂單項目對應的商品
        on_delete=models.CASCADE  # 當商品被刪除時，連帶刪除此 OrderItem
    )
    quantity = models.PositiveIntegerField()  # 訂單中此商品的數量，只允許正整數
    price = models.DecimalField(
        max_digits=10,  # 總共最多 10 位數
        decimal_places=2  # 小數點後 2 位
    )  # 商品價格快照：下單當下的商品單價，用來計算訂單金額，避免後續調價影響歷史訂單