

# Register your models here.
from django.contrib import admin  # 匯入 Django 後台管理模組
from .models import Product, Cart, CartItem, Order, OrderItem  # 匯入本 app 的模型


@admin.register(Product)  # 註冊 Product 模型到 Django admin
class ProductAdmin(admin.ModelAdmin):  # 自訂 Product 在後台的顯示方式
    list_display = ('id', 'name', 'price', 'stock')  # 後台列表要顯示的欄位
    search_fields = ('name',)  # 可搜尋的欄位
    list_filter = ('price',)  # 篩選器（依價格篩選）


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
    list_display = ('id', 'user', 'total_amount', 'status', 'created_at')  # 訂單列表顯示欄位
    list_filter = ('status',)  # 依訂單狀態篩選
    inlines = [OrderItemInline]  # 在訂單頁面中顯示訂單項目


@admin.register(OrderItem)  # 註冊 OrderItem 模型
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ('id', 'order', 'product', 'quantity', 'price')  # 顯示訂單項目資訊