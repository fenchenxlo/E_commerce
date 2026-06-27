from django.db import models  # 從 Django 的 db 模組匯入 models，用來定義資料庫模型

# Create your models here.
from django.contrib.auth.models import User  # 匯入內建的 User 模型，代表系統使用者
from django.core.validators import MinValueValidator, MaxValueValidator
import uuid

# 自訂 Manager：只回傳未下架商品
class ActiveProductManager(models.Manager):
    def get_queryset(self):
        # 覆寫預設查詢，只回傳 is_deleted=False 的商品
        return super().get_queryset().filter(is_deleted=False)
		
class Product(models.Model):
    # 商品唯一 ID（對應 Excel 的 Id）
    # 設 unique=True 可避免重複匯入同一商品
#    product_id = models.CharField(max_length=50, default = 1, unique=True)
    product_id = models.BigAutoField(primary_key=True, unique=True)

    # 商品分類 ID（cateId）
    # 通常用來做分類篩選或關聯分類表
    #cateId = models.IntegerField(max_length=20, null=True, blank=True)
    cateId = models.CharField(
        max_length=50,
        null=True,
        blank=True
    )
    
    # 商品名稱（前台顯示用）
    name = models.CharField(max_length=255)

    # 正規化名稱（regex_name）
    # 用於搜尋、比對（例如去空格、符號）
    regex_name = models.CharField(max_length=255, blank=True, null=True)

    # 商品描述（describe）
    # 可存長文字或 HTML
    description = models.TextField(blank=True, null=True)

    # 商品售價（目前價格）
    price = models.DecimalField(max_digits=10, decimal_places=2)

    # 原價（劃線價）
    # 有些商品沒有原價 → 可為空
    origin_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True
    )

    # 資料來源（例如：pchome、momo、shopee）
    # 用於多平台整合
    source = models.CharField(max_length=50, null=True, blank=True)

    # 資料抓取 / 更新時間
    # 用來判斷資料是否過期
    time = models.DateTimeField(null=True, blank=True)

    # 商品原始頁面 URL
    url = models.TextField(null=True, blank=True)

    # 商品評分（0~5）
    # 加 validator 避免寫入錯誤數值
    rating = models.FloatField(
        null=True,
        blank=True,
        validators=[
            MinValueValidator(0.0),
            MaxValueValidator(5.0)
        ]
    )

    # 評論數量
    # 設 default=0 → 避免 None 判斷問題
    review_count = models.IntegerField(default=0)

    # 銷量
    # 設 default=0 → 方便排序與統計
    sales = models.IntegerField(default=0)

    # 庫存（系統內部用）
    # 與外部電商資料無直接關係
    stock = models.PositiveIntegerField(default=0)
	
	# 新增欄位：商品是否已刪除/下架
    is_deleted = models.BooleanField(default=False, help_text="標記商品是否下架")
	
	
	# 新增欄位：商品擁有者（建立者）
    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="products",
		default = 1, # 代表實際擁有者 userId
        help_text="商品的擁有者（建立者）"
    )
	
    def __str__(self):
        # Django admin / shell 顯示名稱
        return self.name

    class Meta:
        # 建立索引（提升查詢效能）
        # 常用查詢欄位建議加 index
        indexes = [
            models.Index(fields=['product_id']),
            models.Index(fields=['cateId']),
        ]

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
    
    # 訂單狀態可選項目, 前面 是實際存入資料庫的值, 後面是 會在應用程式或是管理介面中顯示
    STATUS_CHOICES = [  
        ('pending', 'Pending'),  # pending：待付款或待處理
        ('waiting_payment', 'Waiting_Payment'),  # 已取得 ATM 虛擬帳號,待付款
        ('expired', 'Expired'),  # 過期未付款
        ('paid', 'Paid'),  # paid：已付款
        ('failed', 'Failed'),  # 付款失敗
        ('shipped', 'Shipped'),  # shipped：已出貨
        ('cancelled', 'Cancelled'),  # cancelled：已取消
    ]
    
    # 新增：訂單編號
    order_number = models.CharField(
        max_length=50,
        unique=True,
        editable=False,
        null=True,
        blank=True
    )
    
    user = models.ForeignKey(
        User,  # 關聯到 User 模型，代表此訂單屬於哪位使用者
        on_delete=models.CASCADE,  # 當使用者被刪除時，連帶刪除其所有訂單
        related_name='order'
    )
    
    # ===== 新增：收件資訊 =====

    receiver_name = models.CharField(
        max_length=100,
        help_text="收件者姓名"
    )

    receiver_phone = models.CharField(
        max_length=20,
        help_text="收件者手機號碼"
    )
    
#     receiver_email = models.EmailField(
#         null=True,
#         blank=True,
#         help_text="收件者 Email"
#     )

    receiver_address = models.TextField(
        help_text="收件地址"
    )
    # 運費
    shipping_fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )
    # 配送狀態
    SHIPPING_STATUS_CHOICES = [
        ('pending', 'Pending'),        # 未出貨
        ('processing', 'Processing'),  # 已出貨
        ('shipped', 'Shipped'),        # 配送中
        ('delivered', 'Delivered'),    # 已送達
        ('returned', 'Returned'),      # 退貨中
    ]

    shipping_status = models.CharField(
        max_length=20,
        choices=SHIPPING_STATUS_CHOICES,
        default='pending'
    )
    # 備註
    remark = models.TextField(
        null=True,
        blank=True,
        help_text="訂單備註"
    )
    
    total_amount = models.DecimalField(
        max_digits=10,  # 總金額最多 10 位數
        decimal_places=2  # 小數點後 2 位
    )  # 訂單總金額，通常由所有 OrderItem 的小計加總而來
    status = models.CharField(
        max_length=20,  # 狀態字串最大長度 10
        choices=STATUS_CHOICES,  # 限制只能是 STATUS_CHOICES 中的其中一個值
        default='pending'  # 預設狀態為 pending（待處理）
    )
    created_at = models.DateTimeField(
        auto_now_add=True  # 在建立訂單時自動填入當下時間，只在第一次建立時設定
    )  # 訂單建立時間
    
#     def save(self, *args, **kwargs):

        # 自動產生訂單編號
#         if not self.order_number:
#             self.order_number = f"ORD-{uuid.uuid4().hex[:10].upper()}"

#         super().save(*args, **kwargs)

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

class Payment(models.Model):
    
    payment_url = models.TextField(
        null=True,
        blank=True
    )

    PAYMENT_STATUS = [
        ('pending', 'Pending'),
        ('success', 'Success'),
        ('failed', 'Failed'),
    ]

#     order = models.OneToOneField(
#         Order,
#         on_delete=models.CASCADE,
#         related_name='payment'
#     )
    
    # 允許同一個訂單有多筆 Payment
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='payments'
    )


    transaction_id = models.CharField(
        max_length=100,
        unique=True
    )

    payment_method = models.CharField(
        max_length=50,
        default='atm'
    )

    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    status = models.CharField(
        max_length=20,
        choices=PAYMENT_STATUS,
        default='pending'
    )

    paid_at = models.DateTimeField(
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    response_data = models.JSONField(
        null=True,
        blank=True
    )
    
    bank_code = models.CharField(max_length=3)                    # 銀行代碼
    v_account = models.CharField(max_length=20)                    # 虛擬銀行帳戶 (通常14-16)
    expire_date = models.DateTimeField()                         # 繳費期限
    
    def __str__(self):
        return f"Payment {self.transaction_id}"