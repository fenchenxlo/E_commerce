

# Register your models here.
from django.contrib import admin  # 匯入 Django 後台管理模組
# 匯入本 app 的模型
from .models import (
    Product,
    Cart,
    CartItem,
    Order,
    OrderItem,
    Payment
)  


# 自訂篩選器：顯示「上架商品 / 已下架商品」
class StatusFilter(admin.SimpleListFilter):
    title = '商品狀態'  # 篩選器標題
    parameter_name = 'status'  # URL query 參數名稱

    def lookups(self, request, model_admin):
        # 定義篩選選項
        return [
            ('active', '上架商品'),
            ('deleted', '已下架商品'),
        ]

    def queryset(self, request, queryset):
        # 根據選項過濾資料
        if self.value() == 'active':
            return queryset.filter(is_deleted=False)
        if self.value() == 'deleted':
            return queryset.filter(is_deleted=True)
        return queryset

@admin.register(Product)  # 註冊 Product 模型到 Django 後台
class ProductAdmin(admin.ModelAdmin):
    # 在列表頁顯示的欄位（很重要，決定後台商品列表頁會看到哪些資訊）
    list_display = (
        'product_id',   # 商品唯一 ID
        'name',
        'regex_name',   # 商品名稱
        'cateId',      # 商品分類 ID
        'price',        # 商品售價
        'origin_price', # 商品原價（劃線價）
        'rating',       # 商品評分
        'review_count', # 評論數量
        'sales',        # 銷售量
        'source',       # 資料來源（例如 momo、pchome）
        'time',         # 資料更新時間
        'is_deleted',   # 顯示下架狀態（True=下架，False=上架）
        'stock',        # 顯示庫存
    )


    # 可點擊進入詳細頁的欄位
    list_display_links = ('product_id', 'name')

    # 右側過濾器
    list_filter = ('source', 'cateId', StatusFilter)  # 可以依下架狀態篩選

    # 搜尋功能（支援模糊搜尋）
    search_fields = ('product_id', 'name', 'regex_name')

    # 預設排序（依銷量 & 評分）
    ordering = ('-sales', '-rating')

    # 每頁顯示筆數
    list_per_page = 20

    # 讓某些欄位唯讀（避免誤改）
    readonly_fields = ('product_id',)

    # 編輯頁欄位分組（美化 UI）
    fieldsets = (
        ('基本資訊', {
            'fields': ('product_id', 'cateId', 'name', 'regex_name', 'description')
        }),
        ('價格資訊', {
            'fields': ('price', 'origin_price')
        }),
        ('評價與銷售', {
            'fields': ('rating', 'review_count', 'sales')
        }),
        ('其他資訊', {
            'fields': ('source', 'time', 'url', 'stock', 'is_deleted')
        }),
    )

	# 自訂管理動作：批次下架 / 上架
    actions = ['mark_deleted', 'mark_active']

    def mark_deleted(self, request, queryset):
        queryset.update(is_deleted=True)
    mark_deleted.short_description = "批次下架選取的商品"

    def mark_active(self, request, queryset):
        queryset.update(is_deleted=False)
    mark_active.short_description = "批次上架選取的商品"

	# 自訂方法：顯示商品狀態（上架中 / 已下架）
    def status_display(self, obj):
        return "已下架" if obj.is_deleted else "上架中"
    status_display.short_description = "狀態"  # 後台欄位名稱
    status_display.admin_order_field = 'is_deleted'  # 允許依 is_deleted 排序
	
@admin.register(Cart)  # 註冊 Cart 模型
class CartAdmin(admin.ModelAdmin):
    list_display = ('id', 'user')  # 顯示購物車 ID 與所屬使用者


@admin.register(CartItem)  # 註冊 CartItem 模型
class CartItemAdmin(admin.ModelAdmin):
    list_display = ('id', 'cart', 'product', 'quantity', 'price')  # 顯示購物車項目資訊


class OrderItemInline(admin.TabularInline):  # 在訂單頁面中以表格方式顯示 OrderItem
    model = OrderItem  # 指定 inline 的模型
    extra = 0  # 不額外顯示空白欄位


@admin.register(Order)  # 註冊 Order 模型
class OrderAdmin(admin.ModelAdmin):
    # 訂單列表顯示欄位
    list_display = (
    'id',
    'order_number',
    'user',
    'total_amount',
    'status',
    'created_at'
    )
    list_filter = (
        'status',
        'created_at'
    )
    # 依訂單狀態篩選
    search_fields = (
    'order_number',
    'user__username',
    )
    
    ordering = ('-created_at',)
    
    inlines = [OrderItemInline]  # 在訂單頁面中顯示訂單項目


@admin.register(OrderItem)  # 註冊 OrderItem 模型
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ('id', 'order', 'product', 'quantity', 'price', 'subtotal')  # 顯示訂單項目資訊
    
    def subtotal(self, obj):
        return obj.quantity * obj.price

    subtotal.short_description = '小計'

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):

    list_display = (
        'id',
        'order',
        'transaction_id',
        'amount',
        'status',
        'payment_method',
        'paid_at',
        'created_at'
    )

    list_filter = (
        'status',
        'payment_method'
    )

    search_fields = (
        'transaction_id',
        'order__order_number',
    )

    ordering = ('-created_at',)