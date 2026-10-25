from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
import uuid


# ============================================================
# Product
# ============================================================

# 自訂 Manager：只回傳未下架商品
class ActiveProductManager(models.Manager):
    def get_queryset(self):
        # 覆寫預設查詢，只回傳 is_deleted=False 的商品
        return super().get_queryset().filter(is_deleted=False)


class Product(models.Model):

    # 商品唯一 ID（對應 Excel 的 Id）
    # 設 unique=True 可避免重複匯入同一商品
    product_id = models.BigAutoField(
        primary_key=True,
        unique=True
    )

    # 商品分類 ID（cateId）
    # 通常用來做分類篩選或關聯分類表
    cateId = models.CharField(
        max_length=50,
        null=True,
        blank=True
    )

    # 商品名稱（前台顯示用）
    name = models.CharField(
        max_length=255
    )

    # 正規化名稱（regex_name）
    # 用於搜尋、比對（例如去空格、符號）
    regex_name = models.CharField(
        max_length=255,
        blank=True,
        null=True
    )

    # 商品描述（describe）
    # 可存長文字或 HTML
    description = models.TextField(
        blank=True,
        null=True
    )

    # 商品售價（目前價格）
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

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
    source = models.CharField(
        max_length=50,
        null=True,
        blank=True
    )

    # 資料抓取 / 更新時間
    # 用來判斷資料是否過期
    time = models.DateTimeField(
        null=True,
        blank=True
    )

    # 商品原始頁面 URL
    url = models.TextField(
        null=True,
        blank=True
    )

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
    review_count = models.IntegerField(
        default=0
    )

    # 銷量
    # 設 default=0 → 方便排序與統計
    sales = models.IntegerField(
        default=0
    )

    # ========================================================
    # 庫存
    # ========================================================

    # 商品目前「可立即購買」的庫存
    #
    # 例如：
    #
    # stock = 7
    # reserved_stock = 3
    #
    # 代表：
    #   可立即購買 = 7
    #   已被訂單預留 = 3
    #   總實體庫存 = 10
    #
    # 【原本欄位，保留】
    stock = models.PositiveIntegerField(
        default=0
    )

    # 【新增】
    # 已被「尚未完成付款的訂單」預留的庫存數量。
    #
    # Checkout 時：
    #
    #   stock -= quantity
    #   reserved_stock += quantity
    #
    # 付款成功：
    #
    #   reserved_stock -= quantity
    #
    # 付款失敗 / 付款逾期：
    #
    #   stock += quantity
    #   reserved_stock -= quantity
    #
    # 這個欄位主要讓庫存狀態更加清楚。
    reserved_stock = models.PositiveIntegerField(
        default=0
    )

    # 商品是否已刪除/下架
    # 【原本欄位，保留】
    is_deleted = models.BooleanField(
        default=False,
        help_text="標記商品是否下架"
    )

    # 商品擁有者（建立者）
    # 【原本欄位，保留】
    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="products",
        default=1,
        help_text="商品的擁有者（建立者）"
    )

    def __str__(self):
        # Django admin / shell 顯示名稱
        return self.name

    class Meta:
        # 建立索引（提升查詢效能）
        indexes = [
            models.Index(fields=['product_id']),
            models.Index(fields=['cateId']),
        ]


# ============================================================
# Cart
# ============================================================

class Cart(models.Model):

    # Cart：購物車模型，每個使用者對應一個購物車
    #
    # 【原本欄位，完整保留】
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE
    )


# ============================================================
# CartItem
# ============================================================

class CartItem(models.Model):

    # CartItem：購物車項目模型，代表購物車中的一筆商品紀錄

    # 【原本欄位，完整保留】
    cart = models.ForeignKey(
        Cart,
        on_delete=models.CASCADE,
        related_name='items'
    )

    # 【原本欄位，完整保留】
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE
    )

    # 購買數量，只允許正整數
    # 【原本欄位，完整保留】
    quantity = models.PositiveIntegerField()

    # 商品價格快照
    #
    # 【原本欄位，完整保留】
    #
    # 注意：
    # 真正具有「訂單交易價格」意義的價格，
    # 最終仍以 OrderItem.price 為準。
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )


# ============================================================
# Order
# ============================================================

class Order(models.Model):

    # ========================================================
    # 訂單狀態
    # ========================================================

    # 【修改】
    #
    # 原本：
    #
    # pending
    # atm_confirmed
    # cod_confirmed
    # expired
    # paid
    # failed
    # shipped
    # cancelled
    #
    # 原本的狀態把「付款狀態」與「訂單狀態」混在一起。
    #
    # 現在 Order.status 專門描述：
    # 「這張訂單目前進行到哪一個階段？」
    #
    STATUS_CHOICES = [

        # 訂單建立完成，等待付款
        ('pending_payment', 'Pending_Payment'),

        # Payment 已經成功
        ('paid', 'Paid'),

        # 商店正在處理訂單
        ('processing', 'Processing'),

        # 已出貨
        ('shipped', 'Shipped'),

        # 訂單已完成
        ('completed', 'Completed'),

        # 訂單已取消
        ('cancelled', 'Cancelled'),

        # 超過付款期限
        ('expired', 'Expired'),
    ]

    # ========================================================
    # 訂單編號
    # ========================================================

    # 【原本欄位，保留】
    order_number = models.CharField(
        max_length=50,
        unique=True,
        editable=False,
        null=True,
        blank=True
    )

    # ========================================================
    # 使用者
    # ========================================================

    # 【原本欄位，保留】
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='order'
    )

    # ========================================================
    # 收件資訊
    # ========================================================

    # 【原本欄位，保留】
    receiver_name = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text="收件者姓名"
    )

    # 【原本欄位，保留】
    receiver_phone = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        help_text="收件者手機號碼"
    )

    # 【原本欄位，保留】
    receiver_address = models.TextField(
        null=True,
        blank=True,
        help_text="收件地址"
    )

    # ========================================================
    # 運費
    # ========================================================

    # 【原本欄位，保留】
    shipping_fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    # ========================================================
    # 配送狀態
    # ========================================================

    # 【原本欄位，保留】
    SHIPPING_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('shipped', 'Shipped'),
        ('delivered', 'Delivered'),
        ('returned', 'Returned'),
    ]

    # 【原本欄位，保留】
    shipping_status = models.CharField(
        max_length=20,
        choices=SHIPPING_STATUS_CHOICES,
        default='pending'
    )

    # ========================================================
    # 訂單備註
    # ========================================================

    # 【原本欄位，保留】
    remark = models.TextField(
        null=True,
        blank=True,
        help_text="訂單備註"
    )

    # ========================================================
    # 金額
    # ========================================================

    # 訂單總金額
    # 通常由：
    #
    # OrderItem 小計
    # +
    # shipping_fee
    #
    # 所計算。
    #
    # 【原本欄位，保留】
    total_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    # ========================================================
    # 訂單狀態
    # ========================================================

    # 【修改】
    # Order.status 現在只負責「訂單生命週期」。
    #
    # Payment 是否成功由 Payment.status 負責。
    status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        default='pending_payment'
    )

    # ========================================================
    # 時間
    # ========================================================

    # 訂單建立時間
    # 【原本欄位，保留】
    created_at = models.DateTimeField(
        auto_now_add=True
    )

    # 【新增】
    # 訂單最後修改時間。
    #
    # 例如：
    #
    # pending_payment
    #       ↓
    # paid
    #       ↓
    # processing
    #       ↓
    # shipped
    #
    # 每次修改 Order 時都會自動更新。
    updated_at = models.DateTimeField(
        auto_now=True
    )

    # ========================================================
    # 付款方式
    # ========================================================

    # 【原本欄位，保留】
    #
    # 注意：
    # payment_method 是「付款方式」
    # 不是 Order.status。
    PAYMENT_METHOD_CHOICES = [
        ("ATM", "ATM 轉帳"),
        ("COD", "超商取貨付款"),
    ]

    payment_method = models.CharField(
        max_length=10,
        choices=PAYMENT_METHOD_CHOICES,
        blank=True,
        default="",
        help_text="使用者實際確認的付款方式"
    )

    # ========================================================
    # 超商取貨資訊
    # ========================================================

    # ========================================================
    # 【刪除】cvs_store_name / cvs_store_address 從 Order 移除，
    # 改放到 Payment（超商取貨資訊屬於付款/取貨方式，不是訂單本身）。
    # 舊資料由 migration 0002 複製到對應的 COD Payment。
    # ========================================================
    # cvs_store_name = models.CharField(
    #     max_length=100,
    #     blank=True,
    #     default="",
    #     help_text="超商取貨付款:使用者確認的取貨門市名稱"
    # )
    #
    # cvs_store_address = models.CharField(
    #     max_length=200,
    #     blank=True,
    #     default="",
    #     help_text="超商取貨付款:使用者確認的取貨門市地址"
    # )

    def save(self, *args, **kwargs):

        # 如果還沒有訂單編號
        if not self.order_number:

            # 產生唯一訂單編號
            self.order_number = (
                f"ORD-{uuid.uuid4().hex[:12].upper()}"
            )

        # 呼叫 Django 原本的 save()
        super().save(*args, **kwargs)
	
	
# ============================================================
# OrderItem
# ============================================================

class OrderItem(models.Model):

    # OrderItem：訂單項目模型，代表訂單中的一筆商品紀錄

    # 【原本欄位，保留】
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='items'
    )

    # 【修改】
    #
    # 原本：
    #
    # on_delete=models.CASCADE
    #
    # 問題：
    # 如果 Product 被刪除，歷史 OrderItem 也會跟著刪除。
    #
    # 電商系統通常不希望歷史訂單消失。
    #
    # 因此改成 PROTECT：
    #
    # 如果商品還存在歷史訂單，
    # Django 不允許直接刪除 Product。
    #
    # 搭配 Product.is_deleted=True
    # 可以達到「商品下架但歷史訂單仍存在」的效果。
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT
    )

    # 【新增】
    #
    # 商品名稱快照。
    #
    # 為什麼需要？
    #
    # 假設今天：
    #
    # Product.name = "iPhone 17"
    #
    # 使用者下單後：
    #
    # Product.name 改成 "iPhone 17 Pro"
    #
    # 歷史訂單仍然應該保留當時的商品名稱。
    name = models.CharField(
        max_length=255
    )

    # 訂單中此商品的數量
    # 【原本欄位，保留】
    quantity = models.PositiveIntegerField()

    # 商品價格快照
    #
    # 這是「真正的訂單成交價格」。
    #
    # Checkout 時把當時 Product.price 寫進來。
    #
    # 即使之後 Product.price 改變，
    # 歷史訂單價格也不會改變。
    #
    # 【原本欄位，保留】
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )


# ============================================================
# Payment
# ============================================================

class Payment(models.Model):

    # ========================================================
    # Payment Provider
    # ========================================================

    # 【新增】
    #
    # 第三方金流 Provider。
    #
    # PaymentService 不直接寫：
    #
    # if ecpay:
    #     ...
    #
    # 而是：
    #
    # Payment.provider
    #       ↓
    # ProviderFactory
    #       ↓
    # ECPayAdapter / StripeAdapter / NewebPayAdapter
    #
    PROVIDER_CHOICES = [
        ('stripe', 'Stripe'),
        ('ecpay', 'ECPay'),
        ('newebpay', 'NewebPay'),
    ]

    provider = models.CharField(
        max_length=20,
        choices=PROVIDER_CHOICES
    )

    # ========================================================
    # Payment ID
    # ========================================================

    # 【新增】
    #
    # 商店自己產生的 Payment 編號。
    #
    # 與第三方金流的交易編號分開。
    payment_number = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False
    )

    # ========================================================
    # 第三方金流交易編號
    # ========================================================

    # 【修改 / 新增】
    #
    # 原本使用 transaction_id。
    #
    # 現在明確區分：
    #
    # payment_number
    #   = 我們商店自己的 Payment ID
    #
    # provider_transaction_id
    #   = Stripe / ECPay / NewebPay 回傳的交易 ID
    #
    provider_transaction_id = models.CharField(
        max_length=150,
        null=True,
        blank=True,
        db_index=True
    )

    # ========================================================
    # Payment URL
    # ========================================================

    # 【原本欄位，保留】
    payment_url = models.TextField(
        null=True,
        blank=True
    )

    # ========================================================
    # Payment Status
    # ========================================================

    # 【修改】
    #
    # 原本：
    #
    # pending
    # success
    # failed
    #
    # 增加：
    #
    # expired
    # cancelled
    #
    # Payment.status 專門表示「付款狀態」。
    PAYMENT_STATUS = [
        ('pending', 'Pending'),
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
    ]

    # ========================================================
    # Order
    # ========================================================

    # 一個 Order 可以有多筆 Payment。
    #
    # 例如：
    #
    # 第一次信用卡付款失敗
    #       ↓
    # Payment #1 = failed
    #
    # 使用者重新付款
    #       ↓
    # Payment #2 = success
    #
    # 因此不能使用 OneToOneField。
    #
    # 【原本設計，保留】
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='payments'
    )

    # ========================================================
    # Payment Method
    # ========================================================

    # 【原本欄位，保留】
    PAYMENT_METHOD_CHOICES = [
        ("ATM", "ATM 轉帳"),
        ("COD", "超商取貨付款"),
    ]

    payment_method = models.CharField(
        max_length=50,
        choices=PAYMENT_METHOD_CHOICES,
        blank=True,
        default="",
        help_text="使用者實際確認的付款方式"
    )

    # ========================================================
    # Amount
    # ========================================================

    # 這一筆 Payment 實際應付金額。
    # 【原本欄位，保留】
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    # ========================================================
    # Status
    # ========================================================

    # 【修改】
    status = models.CharField(
        max_length=20,
        choices=PAYMENT_STATUS,
        default='pending'
    )

    # ========================================================
    # Paid At
    # ========================================================

    # 【原本欄位，保留】
    paid_at = models.DateTimeField(
        null=True,
        blank=True
    )

    # ========================================================
    # Created / Updated
    # ========================================================

    # 【原本欄位，保留】
    created_at = models.DateTimeField(
        auto_now_add=True
    )

    # 【新增】
    # Payment 最後修改時間。
    updated_at = models.DateTimeField(
        auto_now=True
    )

    # ========================================================
    # 第三方金流原始 Response
    # ========================================================

    # 【原本欄位，保留】
    #
    # 可以保存第三方金流 API / Webhook 的原始資料。
    #
    # 注意：
    # 不要把信用卡完整卡號等敏感資料直接保存進來。
    response_data = models.JSONField(
        null=True,
        blank=True
    )

    # ========================================================
    # ATM
    # ========================================================

    # 【原本欄位，保留】
    bank_code = models.CharField(
        max_length=3,
        null=True,
        blank=True
    )

    # 【原本欄位，保留】
    v_account = models.CharField(
        max_length=20,
        null=True,
        blank=True
    )

    # 【原本欄位，保留】
    expire_date = models.DateTimeField(
        null=True,
        blank=True
    )

    # ========================================================
    # 【新增】超商取貨資訊（從 Order 搬移過來）
    # 只有 payment_method = COD 的 Payment 會有值。
    # ========================================================
    cvs_store_name = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="超商取貨付款:使用者確認的取貨門市名稱"
    )

    cvs_store_address = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text="超商取貨付款:使用者確認的取貨門市地址"
    )

    def __str__(self):
        # 【修改】
        # 原本：
        # return f"Payment {self.transaction_id}"
        #
        # 因為現在使用 payment_number 作為商店自己的 Payment ID。
        return f"Payment {self.payment_number}"


# ============================================================
# InventoryReservation
# ============================================================

class InventoryReservation(models.Model):

    # ========================================================
    # Reservation Status
    # ========================================================

    # 【新增 Model】
    #
    # 用來處理：
    #
    # Checkout
    #     ↓
    # 預留庫存
    #     ↓
    # 等待付款
    #
    # Payment Success
    #     ↓
    # committed
    #
    # Payment Failed / Expired
    #     ↓
    # released
    #
    STATUS_CHOICES = [
        # 庫存目前被訂單預留
        ('reserved', 'Reserved'),

        # 付款成功，庫存正式完成銷售
        ('committed', 'Committed'),

        # 付款失敗 / 逾期 / 訂單取消
        # 庫存已經釋放
        ('released', 'Released'),
    ]

    # ========================================================
    # Order
    # ========================================================

    # 【新增】
    #
    # 哪一張 Order 預留了庫存。
    #
    # 一張 Order 可以有多筆 Reservation，
    # 因為一張訂單可能包含多種商品。
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='inventory_reservations'
    )

    # ========================================================
    # Product
    # ========================================================

    # 【新增】
    #
    # 哪一個商品被預留。
    #
    # 使用 PROTECT：
    # 歷史庫存紀錄不應該因為商品刪除而消失。
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name='inventory_reservations'
    )

    # ========================================================
    # Quantity
    # ========================================================

    # 【新增】
    #
    # 此 Reservation 預留多少庫存。
    #
    # 例如：
    #
    # Order #1001
    # Product A
    # quantity = 3
    #
    quantity = models.PositiveIntegerField()

    # ========================================================
    # Status
    # ========================================================

    # 【新增】
    #
    # Reservation 目前狀態。
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='reserved'
    )

    # ========================================================
    # Created At
    # ========================================================

    # 【新增】
    #
    # 庫存預留建立時間。
    created_at = models.DateTimeField(
        auto_now_add=True
    )

    # ========================================================
    # Expires At
    # ========================================================

    # 【新增】
    #
    # 預留期限。
    #
    # 例如 ATM：
    #
    # 2026-09-03 20:00
    #       ↓
    # 2026-09-04 23:59
    #
    # 超過期限仍未付款：
    #
    # Reservation → released
    # Stock → release
    #
    expires_at = models.DateTimeField(
        null=True,
        blank=True
    )

    # ========================================================
    # Updated At
    # ========================================================

    # 【新增】
    #
    # Reservation 最後修改時間。
    updated_at = models.DateTimeField(
        auto_now=True
    )

    def __str__(self):
        return (
            f"Reservation "
            f"Order={self.order.order_number} "
            f"Product={self.product.name} "
            f"Qty={self.quantity} "
            f"Status={self.status}"
        )