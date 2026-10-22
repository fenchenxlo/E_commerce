# E_commerce（商店）— 分層重要程式碼

> **閱讀說明**：本文件由原始碼自動擷取（AST），只保留「重要流程的程式碼」，已移除 docstring 與註解並重新排版（縮排、引號可能與原檔略有不同），僅供閱讀與理解架構；實際修改請以原始檔為準。每段標題附有原檔行號。
> 擷取來源：`E-Shop_Api_1012.zip`（2026-10-14 最新版）：含取消訂單、ATM 取消守衛、刪除同步、金額重算。

## 專案定位
主購物站（Django + SQLite，HF Space）。負責：商品 / 購物車 / 訂單 / 付款紀錄 / 庫存預留，並以 httpx 呼叫 **ecpay_mock**、接收其 callback。

## 呼叫關係
```
買家瀏覽器 ─► views / api（入口、流程控制）
                 └► services（商業邏輯）
                       └► interfaces（抽象 ABC）
                             └► adapters（httpx → ecpay_mock；僅 Order_service 還有用 OrderRepository 做 ORM，PaymentRepository 已不使用）
ecpay_mock ──callback──► atm_payment_notify / cod_payment_notify / cod_store_confirmed
```

## 兩條付款流程（本專案角色）
- **ATM**：`/api/checkout` → OrderService → PaymentService → ECPayMockAdapter → ecpay_mock；結果由 `atm_payment_notify` 回來。
- **COD**：選超商後由 ecpay_mock `cod_gateway` 回傳 `cod_store_confirmed` / `cod_payment_notify`。
- **取消訂單**：`cancel_order` view → `PaymentService.cancel_order` → `ECPayMockAdapter.cancel_payment`（ATM / COD 不同端點）。

## 重要環境變數
`HF_SPACE_E_COMMERCE_URL` / `HF_SPACE_ECPAY_MOCK_URL` / `HF_SPACE_BANK_SITE_URL`、`ECPAY_HASH_KEY` / `ECPAY_HASH_IV`、`SQLITE_DB_PATH`。

## 狀態對照
| Order.status | 意義 |
|---|---|
| pending_payment | 待處理（含 ATM 待付款、COD 待出貨 / 取貨失敗） |
| paid / shipped / expired / cancelled / failed | 已付款 / 配送中(COD) / 逾期 / 已取消 / 付款失敗 |

Payment.status：pending / success / failed / expired / cancelled


---

## 目錄

1. [路由層 Routing](#layer-1)
2. [資料模型層 Models](#layer-2)
3. [Schema 層](#layer-3)
4. [入口層 Views / API（流程控制）](#layer-4)
5. [服務層 Services（商業邏輯）](#layer-5)
6. [介面層 Interfaces（抽象 ABC）](#layer-6)
7. [轉接層 Adapters（httpx；僅 OrderRepository 用 ORM）](#layer-7)

---

<a id="layer-1"></a>

## 1. 路由層 Routing

URL 對應到 view。`commerce_shop/urls.py` 是所有商店功能入口。

### 📄 `E_commerce/E_commerce/urls.py`

```python
from django.contrib import admin
from django.urls import path, include
from commerce_shop.views import home
from commerce_shop.api import api
urlpatterns = [
    path('admin/', admin.site.urls),
    path('', home, name='home'),
    path('commerce_shop/', include('commerce_shop.urls')),
    path('e_commerce_account/', include('allauth.urls')),
    path('accounts/', include('allauth.urls')),
    path('api/', api.urls),
]
```

### 📄 `E_commerce/commerce_shop/urls.py`

```python
from django.urls import path
from commerce_shop.views import api_search, db_query_tool, product_list, add_to_cart, cart_detail, cart_checkout_page, purchased_products, enter_receiver_info, atm_payment_notify, cod_payment_notify, cod_store_confirmed, delete_order_item, delete_order, cancel_order, update_cart_item, remove_cart_item, ready_form, ecpay_checkout_redirect, payment_error, payment_callback, ecpay_mock_notify, payment_ok, download_orderPayment_json
urlpatterns = [
    path('api_search/', api_search, name='api_search'),
    path('admin-tools/query/', db_query_tool, name='db_query_tool'),
    path('products/', product_list, name='product_list'),
    path('products/add/<int:product_id>/', add_to_cart, name='add_to_cart'),
    path('cart/', cart_detail, name='cart_detail'),
    path('cart/update/<int:product_id>/', update_cart_item, name='update_cart_item'),
    path('cart/remove/<int:product_id>/', remove_cart_item, name='remove_cart_item'),
    path('cart_checkout_page/', cart_checkout_page, name='cart_checkout_page'),
    path('enter_receiver_info/<str:order_number>/', enter_receiver_info, name='enter_receiver_info'),
    path('purchased_products/', purchased_products, name='purchased_products'),
    path('delete_order/<int:order_id>/', delete_order, name='delete_order'),
    path('cancel_order/<int:order_id>/', cancel_order, name='cancel_order'),
    path('delete_order_item/<int:order_item_id>/', delete_order_item, name='delete_order_item'),
    path('atm_payment_notify/', atm_payment_notify, name='atm_payment_notify'),
    path('cod_payment_notify/', cod_payment_notify, name='cod_payment_notify'),
    path('cod_store_confirmed/', cod_store_confirmed, name='cod_store_confirmed'),
    path('payment_error/', payment_error, name='payment_error'),
    path('payment_callback/', payment_callback, name='payment_callback'),
    path('ecpay_mock_notify/', ecpay_mock_notify, name='ecpay_mock_notify'),
    path('payment_ok/', payment_ok, name='payment_ok'),
    path('ready_form/', ready_form, name='ready_form'),
    path('ecpay_checkout_redirect/', ecpay_checkout_redirect, name='ecpay_checkout_redirect'),
    path('download_orderPayment_json/', download_orderPayment_json, name='download_orderPayment_json'),
]
```

<a id="layer-2"></a>

## 2. 資料模型層 Models

Product / Cart / Order / Payment / InventoryReservation 等 ORM 模型。

### 📄 `E_commerce/commerce_shop/models.py`

#### `ActiveProductManager`（class，原檔第 12–15 行）

```python
class ActiveProductManager(models.Manager):

    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)
```

#### `Product`（class，原檔第 18–183 行）

```python
class Product(models.Model):
    product_id = models.BigAutoField(primary_key=True, unique=True)
    cateId = models.CharField(max_length=50, null=True, blank=True)
    name = models.CharField(max_length=255)
    regex_name = models.CharField(max_length=255, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    origin_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    source = models.CharField(max_length=50, null=True, blank=True)
    time = models.DateTimeField(null=True, blank=True)
    url = models.TextField(null=True, blank=True)
    rating = models.FloatField(null=True, blank=True, validators=[MinValueValidator(0.0), MaxValueValidator(5.0)])
    review_count = models.IntegerField(default=0)
    sales = models.IntegerField(default=0)
    stock = models.PositiveIntegerField(default=0)
    reserved_stock = models.PositiveIntegerField(default=0)
    is_deleted = models.BooleanField(default=False, help_text='標記商品是否下架')
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='products', default=1, help_text='商品的擁有者（建立者）')

    def __str__(self):
        return self.name

    class Meta:
        indexes = [models.Index(fields=['product_id']), models.Index(fields=['cateId'])]
```

#### `Cart`（class，原檔第 190–198 行）

```python
class Cart(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
```

#### `CartItem`（class，原檔第 205–236 行）

```python
class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
```

#### `Order`（class，原檔第 243–501 行）

```python
class Order(models.Model):
    STATUS_CHOICES = [('pending_payment', 'Pending_Payment'), ('paid', 'Paid'), ('processing', 'Processing'), ('shipped', 'Shipped'), ('completed', 'Completed'), ('cancelled', 'Cancelled'), ('expired', 'Expired')]
    order_number = models.CharField(max_length=50, unique=True, editable=False, null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='order')
    receiver_name = models.CharField(max_length=100, null=True, blank=True, help_text='收件者姓名')
    receiver_phone = models.CharField(max_length=20, null=True, blank=True, help_text='收件者手機號碼')
    receiver_address = models.TextField(null=True, blank=True, help_text='收件地址')
    shipping_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    SHIPPING_STATUS_CHOICES = [('pending', 'Pending'), ('processing', 'Processing'), ('shipped', 'Shipped'), ('delivered', 'Delivered'), ('returned', 'Returned')]
    shipping_status = models.CharField(max_length=20, choices=SHIPPING_STATUS_CHOICES, default='pending')
    remark = models.TextField(null=True, blank=True, help_text='訂單備註')
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='pending_payment')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    PAYMENT_METHOD_CHOICES = [('ATM', 'ATM 轉帳'), ('COD', '超商取貨付款')]
    payment_method = models.CharField(max_length=10, choices=PAYMENT_METHOD_CHOICES, blank=True, default='', help_text='使用者實際確認的付款方式')

    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = f'ORD-{uuid.uuid4().hex[:12].upper()}'
        super().save(*args, **kwargs)
```

#### `OrderItem`（class，原檔第 508–578 行）

```python
class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    name = models.CharField(max_length=255)
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
```

#### `Payment`（class，原檔第 585–846 行）

```python
class Payment(models.Model):
    PROVIDER_CHOICES = [('stripe', 'Stripe'), ('ecpay', 'ECPay'), ('newebpay', 'NewebPay')]
    provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES)
    payment_number = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    provider_transaction_id = models.CharField(max_length=150, null=True, blank=True, db_index=True)
    payment_url = models.TextField(null=True, blank=True)
    PAYMENT_STATUS = [('pending', 'Pending'), ('success', 'Success'), ('failed', 'Failed'), ('expired', 'Expired'), ('cancelled', 'Cancelled')]
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='payments')
    PAYMENT_METHOD_CHOICES = [('ATM', 'ATM 轉帳'), ('COD', '超商取貨付款')]
    payment_method = models.CharField(max_length=50, choices=PAYMENT_METHOD_CHOICES, blank=True, default='', help_text='使用者實際確認的付款方式')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS, default='pending')
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    response_data = models.JSONField(null=True, blank=True)
    bank_code = models.CharField(max_length=3, null=True, blank=True)
    v_account = models.CharField(max_length=20, null=True, blank=True)
    expire_date = models.DateTimeField(null=True, blank=True)
    cvs_store_name = models.CharField(max_length=100, blank=True, default='', help_text='超商取貨付款:使用者確認的取貨門市名稱')
    cvs_store_address = models.CharField(max_length=200, blank=True, default='', help_text='超商取貨付款:使用者確認的取貨門市地址')

    def __str__(self):
        return f'Payment {self.payment_number}'
```

#### `InventoryReservation`（class，原檔第 853–1003 行）

```python
class InventoryReservation(models.Model):
    STATUS_CHOICES = [('reserved', 'Reserved'), ('committed', 'Committed'), ('released', 'Released')]
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='inventory_reservations')
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='inventory_reservations')
    quantity = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='reserved')
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'Reservation Order={self.order.order_number} Product={self.product.name} Qty={self.quantity} Status={self.status}'
```

### 📄 `E_commerce/e_commerce_account/models.py`

#### `UserProfile`（class，原檔第 8–28 行）

```python
class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(null=True, blank=True)
    address = models.CharField(max_length=255, blank=True)
    birthday = models.DateField(null=True, blank=True)
    is_Vip = models.BooleanField(default=False, blank=True)

    def __str__(self):
        return self.user.username
```

<a id="layer-3"></a>

## 3. Schema 層

Django Ninja 的請求資料驗證。

### 📄 `E_commerce/commerce_shop/schemas/first_checkout.py`

#### `FirstCheckoutSchema`（class，原檔第 4–24 行）
> 第一次 Checkout。

```python
class FirstCheckoutSchema(Schema):
    stage: int = 1
```

### 📄 `E_commerce/commerce_shop/schemas/receiver_checkout.py`

#### `SecondCheckoutSchema`（class，原檔第 8–75 行）
> 第二次 Checkout。

```python
class SecondCheckoutSchema(Schema):
    order_number: str = Field(min_length=1, max_length=50)
    receiver_name: str = Field(min_length=1, max_length=100)
    receiver_phone: str = Field(min_length=8, max_length=20)
    receiver_address: str = Field(min_length=1)
    remark: str | None = None
    payment_method: Literal['ATM', 'COD']
    shipping_fee: Decimal = Field(default=Decimal('60'), ge=0)
    stage: int = 2
```

### 📄 `E_commerce/commerce_shop/schemas/checkout.py`

#### `CheckoutSchema`（class，原檔第 63–202 行）

```python
class CheckoutSchema(Schema):
    model_config = ConfigDict(extra='forbid')
    order_number: str = Field(min_length=1, max_length=50)
    receiver_name: str = Field(min_length=1, max_length=100, null=True, blank=True)
    receiver_phone: str = Field(min_length=8, max_length=20, null=True, blank=True)
    receiver_address: str = Field(min_length=1, max_length=500, null=True, blank=True)
    payment_method: str = Field(min_length=3, max_length=3)
    remark: str = Field(default='', max_length=500, null=True, blank=True)
    shipping_fee: Decimal = Field(default=Decimal('0.00'), ge=Decimal('0.00'))
```

<a id="layer-4"></a>

## 4. 入口層 Views / API（流程控制）

只收 request、呼叫 service、導頁；包含 callback 入口與取消訂單。

### 📄 `E_commerce/commerce_shop/api.py`

#### `checkout`（def，原檔第 34–289 行）
> 【修改】

```python
@api.post('/checkout')
def checkout(request, data: CheckoutSchema):
    if not request.user.is_authenticated:
        return JsonResponse({'success': False, 'message': '請先登入會員。'}, status=401)
    try:
        order_service = OrderService()
        order_result = order_service.process_existing_order_checkout(user=request.user, payload=data)
        if data.payment_method == 'COD':
            return JsonResponse(order_result, status=200)
        return JsonResponse({'success': True, 'order_number': order_result['order_number'], 'order_status': order_result['status'], 'payment_method': order_result['payment_method'], 'message': '訂單資料更新成功，準備前往 ECPay ATM 付款。'}, status=200)
    except ValueError as exc:
        logger.warning('[checkout] 業務錯誤：%s', exc)
        return JsonResponse({'success': False, 'error_type': type(exc).__name__, 'message': str(exc)}, status=400)
    except Exception as exc:
        logger.exception('[checkout] Checkout 發生未預期錯誤')
        return JsonResponse({'success': False, 'error_type': type(exc).__name__, 'message': str(exc)}, status=500)
```

### 📄 `E_commerce/commerce_shop/views.py`

#### `add_to_cart`（def，原檔第 336–379 行）

```python
@login_required
def add_to_cart(request, product_id):
    try:
        product = get_object_or_404(Product, product_id=product_id)
        CartService.add_product(user=request.user, product=product, quantity=1)
        messages.success(request, f'{product.name} 已加入購物車。')
    except ValueError as exc:
        messages.error(request, str(exc))
    except Exception as exc:
        logger.exception('[add_to_cart] 加入購物車失敗')
        messages.error(request, '加入購物車失敗。')
    return redirect('cart_detail')
```

#### `cart_detail`（def，原檔第 1800–1826 行）

```python
@login_required
def cart_detail(request):
    cart, created = Cart.objects.get_or_create(user=request.user)
    cart_items = cart.items.all()
    for item in cart_items:
        item.subtotal = item.price * item.quantity
    total_price = sum((item.subtotal for item in cart_items))
    return render(request, 'cart.html', {'cart_items': cart_items, 'total_price': total_price, 'backend_url': BACKEND_URL})
```

#### `cart_checkout_page`（def，原檔第 2078–2114 行）
> 購物車結帳功能（將 Cart/CartItem 轉換並寫入 Order/OrderItem）

```python
@login_required
@require_POST
def cart_checkout_page(request):
    if not request.user.is_authenticated:
        return JsonResponse({'success': False, 'message': '請先登入。'}, status=401)
    try:
        user_cart = Cart.objects.filter(user=request.user).first()
        if not user_cart or not user_cart.items.exists():
            messages.error(request, '您的購物車是空的，無法結帳。')
            return redirect('cart_detail')
        order = OrderService.checkout(user=request.user, cart=user_cart)
        messages.success(request, f'訂單建立成功！您的訂單編號為：{order.order_number}')
        return redirect('purchased_products')
    except ValueError as e:
        messages.error(request, str(e))
        return redirect('cart_detail')
    except Exception as e:
        logger.exception('[cart_checkout_page] 建立訂單時發生系統錯誤')
        messages.error(request, '建立訂單時發生系統錯誤，請稍後再試。')
        return redirect('cart_detail')
```

#### `enter_receiver_info`（def，原檔第 1478–1539 行）
> 【修改】

```python
@login_required
def enter_receiver_info(request, order_number):
    order = get_object_or_404(Order, order_number=order_number, user=request.user)
    if order.status == 'expired':
        messages.error(request, '此訂單已逾期未付款，無法再付款，請重新下單。')
        return redirect('purchased_products')
    return render(request, 'enter_receiver_info.html', {'order_number': order_number, 'order': order, 'HF_SPACE_E_COMMERCE_URL': HF_SPACE_E_COMMERCE_URL})
```

#### `purchased_products`（def，原檔第 2403–2587 行）
> 【修改】

```python
@login_required
def purchased_products(request):
    from commerce_shop.services.order_query_service import OrderQueryService
    try:
        orders = OrderQueryService.get_user_orders(request.user)
        order_list = []
        for order in orders:
            items_with_subtotal = []
            order_total = 0
            for item in order.items.all():
                subtotal = item.price * item.quantity
                order_total += subtotal
                items_with_subtotal.append({'item': item, 'subtotal': subtotal})
            total_with_shipping = order_total + order.shipping_fee
            atm_payment = None
            if order.payment_method == 'ATM':
                atm_payments = getattr(order, 'atm_payments', [])
                if atm_payments:
                    atm_payment = atm_payments[0]
            cod_payment = None
            if order.payment_method == 'COD':
                cod_payment = order.payments.filter(payment_method='COD').order_by('-created_at').first()
            latest_payment = order.payments.order_by('-created_at').first()
            order_list.append({'order': order, 'items': items_with_subtotal, 'shipping_fee': order.shipping_fee, 'total_with_shipping': total_with_shipping, 'payment_method': order.payment_method, 'latest_payment': latest_payment, 'cod_payment': cod_payment, 'payment_bank_code': atm_payment.bank_code if atm_payment else '', 'payment_v_account': atm_payment.v_account if atm_payment else '', 'payment_expire_date': atm_payment.expire_date if atm_payment else None})
        return render(request, 'purchased_products.html', {'order_list': order_list, 'backend_url': BACKEND_URL})
    except Exception as exc:
        logger.exception('[purchased_products] 顯示訂單失敗')
        return render(request, 'purchased_products.html', {'order_list': [], 'load_error': '讀取訂單失敗，請稍後再試。'})
```

#### `delete_order_item`（def，原檔第 2887–2942 行）
> 刪除「單一商品列（OrderItem）」並恢復庫存

```python
@login_required
def delete_order_item(request, order_item_id):
    item = get_object_or_404(OrderItem, id=order_item_id, order__user=request.user)
    order = item.order
    if order.status in ['shipped', 'paid', 'expired'] or (order.status != 'cancelled' and order.payments.exists()):
        messages.error(request, '已付款、已出貨或已逾期的訂單商品無法刪除；已建立付款資訊的訂單請先按「取消訂單」。')
        return redirect('purchased_products')
    if request.method == 'POST':
        with transaction.atomic():
            product = item.product
            if order.status != 'cancelled':
                product.stock += item.quantity
                product.reserved_stock = max(product.reserved_stock - item.quantity, 0)
                order.inventory_reservations.filter(product=product, status='reserved').update(status='released')
            product.save()
            item.delete()
            if not order.items.exists():
                order.delete()
            else:
                order.total_amount = sum((i.price * i.quantity for i in order.items.all())) + order.shipping_fee
                order.save(update_fields=['total_amount', 'updated_at'])
        messages.success(request, '商品已成功從訂單移除')
        return redirect('purchased_products')
    return render(request, 'confirm_delete_item.html', {'item': item})
```

#### `delete_order`（def，原檔第 2945–2974 行）

```python
@login_required
def delete_order(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)
    if order.status not in ['pending_payment']:
        messages.error(request, '只有待付款的訂單可以刪除。')
        return redirect('purchased_products')
    if request.method == 'POST':
        try:
            PaymentService().cancel_order(order)
        except Exception as ex:
            logger.exception('刪除訂單前同步取消失敗：order_id=%s', order_id)
            messages.error(request, f'刪除失敗，無法同步取消付款資訊：{ex}')
            return redirect('purchased_products')
        with transaction.atomic():
            for res in order.inventory_reservations.select_related('product').filter(status='reserved'):
                product = res.product
                product.stock += res.quantity
                product.reserved_stock -= res.quantity
                product.save()
            order_number = order.order_number
            order.delete()
        messages.success(request, f'訂單 #{order_number} 已刪除,商品庫存已恢復。')
        return redirect('purchased_products')
    return render(request, 'confirm_delete_order.html', {'order': order})
```

#### `cancel_order`（def，原檔第 3008–3025 行）

```python
@login_required
def cancel_order(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)
    if request.method != 'POST':
        return redirect('purchased_products')
    try:
        PaymentService().cancel_order(order)
    except ValueError as ex:
        messages.error(request, str(ex))
    except Exception as ex:
        logger.exception('取消訂單失敗：order_id=%s', order_id)
        messages.error(request, f'取消訂單失敗：{ex}')
    else:
        messages.success(request, f'訂單 #{order.order_number} 已取消，商品庫存已恢復。')
    return redirect('purchased_products')
```

#### `update_cart_item`（def，原檔第 3028–3068 行）

```python
@login_required
def update_cart_item(request, product_id):
    product = get_object_or_404(Product, product_id=product_id)
    try:
        cart = Cart.objects.get(user=request.user)
    except Cart.DoesNotExist:
        messages.error(request, '購物車不存在')
        return redirect('cart_detail')
    try:
        cart_item = CartItem.objects.get(cart=cart, product=product)
    except CartItem.DoesNotExist:
        messages.error(request, '購物車中沒有這個商品')
        return redirect('cart_detail')
    if request.method == 'POST':
        try:
            quantity = int(request.POST.get('quantity'))
        except (TypeError, ValueError):
            messages.error(request, '數量輸入錯誤')
            return redirect('cart_detail')
        if quantity < 1:
            messages.error(request, '數量不能小於 1')
        elif quantity > product.stock:
            messages.error(request, f'庫存不足，最多只能購買 {product.stock} 個')
        else:
            cart_item.quantity = quantity
            cart_item.save()
            messages.success(request, f'{product.name} 的數量已更新為 {quantity}')
    return redirect('cart_detail')
```

#### `remove_cart_item`（def，原檔第 3072–3092 行）
> 刪除購物車商品

```python
@login_required
def remove_cart_item(request, product_id):
    product = get_object_or_404(Product, product_id=product_id)
    if request.method == 'POST':
        try:
            cart = Cart.objects.get(user=request.user)
        except Cart.DoesNotExist:
            messages.error(request, '購物車不存在')
            return redirect('cart_detail')
        cart_item = CartItem.objects.filter(cart=cart, product=product).first()
        if cart_item:
            cart_item.delete()
            messages.success(request, f'{product.name} 已從購物車移除')
        else:
            messages.warning(request, f'{product.name} 不在你的購物車中')
    return redirect('cart_detail')
```

#### `atm_payment_notify`（def，原檔第 531–847 行）
> 【修改】

```python
@csrf_exempt
def atm_payment_notify(request):
    if request.method != 'POST':
        return JsonResponse({'status': False, 'success': False, 'message': 'Method Not Allowed'}, status=405)
    try:
        if request.body:
            raw_body = request.body.decode('utf-8')
            data = json.loads(raw_body)
        elif request.POST:
            data = request.POST.dict()
        else:
            data = {}
        if not isinstance(data, dict):
            raise ValueError('callback payload 必須是 JSON object')
    except json.JSONDecodeError as exc:
        logger.warning('ATM callback JSON 格式錯誤：%s', exc)
        return JsonResponse({'status': False, 'success': False, 'message': 'JSON 格式錯誤'}, status=400)
    except Exception as exc:
        logger.exception('ATM callback request parse 失敗')
        return JsonResponse({'status': False, 'success': False, 'message': 'callback request 格式錯誤', 'error': str(exc)}, status=400)
    verify_payload = dict(data)
    received_mac = verify_payload.pop('CheckMacValue', None)
    if received_mac is None:
        received_mac = verify_payload.pop('check_mac_value', None)
    if not received_mac:
        logger.warning('ATM callback 缺少 CheckMacValue')
        return JsonResponse({'status': False, 'success': False, 'message': '缺少 CheckMacValue'}, status=400)
    try:
        expected_mac = generate_check_mac_value(verify_payload, settings.ECPAY_HASH_KEY, settings.ECPAY_HASH_IV)
    except Exception as exc:
        logger.exception('ATM callback CheckMacValue 計算失敗')
        return JsonResponse({'status': False, 'success': False, 'message': 'CheckMacValue 驗證失敗', 'error': str(exc)}, status=400)
    if not hmac.compare_digest(str(received_mac), str(expected_mac)):
        logger.warning('ATM callback CheckMacValue 不一致')
        return JsonResponse({'status': False, 'success': False, 'message': 'CheckMacValue Error'}, status=400)
    service = PaymentService()
    try:
        result = service.handle_atm_callback(data)
    except ValueError as exc:
        logger.warning('ATM callback business validation 失敗：%s', exc)
        return JsonResponse({'status': False, 'success': False, 'message': str(exc)}, status=400)
    except RuntimeError as exc:
        logger.exception('ATM callback Service 處理失敗')
        return JsonResponse({'status': False, 'success': False, 'message': str(exc)}, status=500)
    except Exception as exc:
        logger.exception('ATM callback 發生未預期錯誤')
        return JsonResponse({'status': False, 'success': False, 'message': 'ATM callback 處理失敗', 'error': str(exc)}, status=500)
    return JsonResponse(result, status=200)
```

#### `cod_payment_notify`（def，原檔第 855–907 行）

```python
@csrf_exempt
def cod_payment_notify(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Method Not Allowed'}, status=405)
    try:
        data = json.loads(request.body.decode('utf-8')) if request.body else {}
        if not isinstance(data, dict):
            raise ValueError('callback payload 必須是 JSON object')
    except Exception as exc:
        return JsonResponse({'success': False, 'message': f'callback request 格式錯誤：{exc}'}, status=400)
    verify_payload = dict(data)
    received_mac = verify_payload.pop('CheckMacValue', None) or verify_payload.pop('check_mac_value', None)
    verify_payload.pop('check_mac_value', None)
    if not received_mac:
        return JsonResponse({'success': False, 'message': '缺少 CheckMacValue'}, status=400)
    expected_mac = generate_check_mac_value(verify_payload, settings.ECPAY_HASH_KEY, settings.ECPAY_HASH_IV)
    if not hmac.compare_digest(str(received_mac), str(expected_mac)):
        logger.warning('COD callback CheckMacValue 不一致')
        return JsonResponse({'success': False, 'message': 'CheckMacValue Error'}, status=400)
    try:
        result = PaymentService().handle_cod_callback(verify_payload)
    except ValueError as exc:
        logger.warning('COD callback business validation 失敗：%s', exc)
        return JsonResponse({'success': False, 'message': str(exc)}, status=400)
    except Exception as exc:
        logger.exception('COD callback 處理失敗')
        return JsonResponse({'success': False, 'message': 'COD callback 處理失敗', 'error': str(exc)}, status=500)
    return JsonResponse(result, status=200)
```

#### `cod_store_confirmed`（def，原檔第 1013–1144 行）

```python
@csrf_exempt
def cod_store_confirmed(request):
    if request.method != 'POST':
        return HttpResponse('method error', status=405)
    try:
        data = json.loads(request.body)
        recv_mac = data.pop('check_mac_value', '')
        from util.ChkMacVal import generate_check_mac_value
        local_mac = generate_check_mac_value(data, settings.ECPAY_HASH_KEY, settings.ECPAY_HASH_IV)
        if recv_mac != local_mac:
            return JsonResponse({'status': 'error', 'message': 'CheckMacValue Error'}, status=400)
        from .models import Order
        order = Order.objects.filter(order_number=data['merchant_trade_no']).first()
        if order is None:
            return JsonResponse({'status': 'error', 'message': '找不到對應訂單'}, status=404)
        from django.db import transaction
        with transaction.atomic():
            order.payment_method = 'COD'
            order.save(update_fields=['payment_method', 'updated_at'])
            cod_payment = order.payments.filter(payment_method='COD').order_by('-created_at').first()
            if cod_payment:
                cod_payment.cvs_store_name = data.get('store_name', '')
                cod_payment.cvs_store_address = data.get('store_address', '')
                cod_payment.save(update_fields=['cvs_store_name', 'cvs_store_address', 'updated_at'])
        return JsonResponse({'status': 'success'})
    except Exception as exc:
        logger.exception('[cod_store_confirmed] callback failed')
        return JsonResponse({'status': 'error', 'message': str(exc)}, status=500)
```

<a id="layer-5"></a>

## 5. 服務層 Services（商業邏輯）

訂單建立、付款、庫存、callback 處理、取消訂單。

### 📄 `E_commerce/commerce_shop/services/cart_service.py`

#### `CartService`（class，原檔第 11–200 行）
> 【新增】

```python
class CartService:

    @staticmethod
    def get_or_create_cart(user):
        cart, created = Cart.objects.get_or_create(user=user)
        return cart

    @staticmethod
    def get_cart_items(user):
        cart = CartService.get_or_create_cart(user)
        return cart.items.select_related('product').all()

    @staticmethod
    @transaction.atomic
    def add_product(user, product, quantity=1):
        cart = CartService.get_or_create_cart(user)
        cart_item, created = CartItem.objects.get_or_create(cart=cart, product=product, defaults={'quantity': quantity, 'price': product.price})
        if not created:
            new_quantity = cart_item.quantity + quantity
            if new_quantity > product.stock:
                raise ValueError(f'庫存不足，最多只能購買 {product.stock} 個。')
            cart_item.quantity = new_quantity
            cart_item.save(update_fields=['quantity'])
        elif product.stock < quantity:
            cart_item.delete()
            raise ValueError(f'商品「{product.name}」庫存不足。')
        return cart_item

    @staticmethod
    @transaction.atomic
    def update_quantity(user, product_id, quantity):
        cart = CartService.get_or_create_cart(user)
        cart_item = CartItem.objects.select_related('product').get(cart=cart, product_id=product_id)
        if quantity <= 0:
            cart_item.delete()
            return None
        if quantity > cart_item.product.stock:
            raise ValueError(f'庫存不足，目前可用庫存：{cart_item.product.stock}')
        cart_item.quantity = quantity
        cart_item.save(update_fields=['quantity'])
        return cart_item

    @staticmethod
    @transaction.atomic
    def remove_item(user, product_id):
        cart = CartService.get_or_create_cart(user)
        deleted, _ = CartItem.objects.filter(cart=cart, product_id=product_id).delete()
        return deleted

    @staticmethod
    @transaction.atomic
    def clear_cart(user):
        cart = CartService.get_or_create_cart(user)
        cart.items.all().delete()

    @staticmethod
    def calculate_total(user):
        items = CartService.get_cart_items(user)
        return sum((item.price * item.quantity for item in items))
```

### 📄 `E_commerce/commerce_shop/services/inventory_service.py`

#### `InventoryService`（class，原檔第 15–247 行）
> 【新增】

```python
class InventoryService:
    RESERVATION_MINUTES = 30

    @staticmethod
    @transaction.atomic
    def reserve_order_inventory(order):
        order_items = OrderItem.objects.select_related('product').select_for_update().filter(order=order)
        for order_item in order_items:
            product = order_item.product
            quantity = order_item.quantity
            if product.stock < quantity:
                raise ValueError(f'商品「{product.name}」庫存不足，目前可用庫存：{product.stock}，需要：{quantity}')
            product.stock -= quantity
            product.reserved_stock += quantity
            product.save(update_fields=['stock', 'reserved_stock'])
            InventoryReservation.objects.create(order=order, product=product, quantity=quantity, status='reserved', expires_at=timezone.now() + timedelta(minutes=InventoryService.RESERVATION_MINUTES))

    @staticmethod
    @transaction.atomic
    def commit_order_inventory(order):
        reservations = InventoryReservation.objects.select_related('product').select_for_update().filter(order=order, status='reserved')
        for reservation in reservations:
            product = Product.objects.select_for_update().get(product_id=reservation.product.product_id)
            if product.reserved_stock < reservation.quantity:
                raise ValueError(f'商品「{product.name}」reserved_stock 資料異常。')
            product.reserved_stock -= reservation.quantity
            product.save(update_fields=['reserved_stock'])
            reservation.status = 'committed'
            reservation.updated_at = timezone.now()
            reservation.save(update_fields=['status', 'updated_at'])

    @staticmethod
    @transaction.atomic
    def release_order_inventory(order):
        reservations = InventoryReservation.objects.select_related('product').select_for_update().filter(order=order, status='reserved')
        for reservation in reservations:
            product = Product.objects.select_for_update().get(product_id=reservation.product.product_id)
            if product.reserved_stock < reservation.quantity:
                raise ValueError(f'商品「{product.name}」reserved_stock 資料異常。')
            product.stock += reservation.quantity
            product.reserved_stock -= reservation.quantity
            product.save(update_fields=['stock', 'reserved_stock'])
            reservation.status = 'released'
            reservation.updated_at = timezone.now()
            reservation.save(update_fields=['status', 'updated_at'])
```

### 📄 `E_commerce/commerce_shop/services/order_service.py`

#### `OrderService`（class，原檔第 31–1365 行）
> Order Business Service。

```python
class OrderService:
    SHIPPING_FEE = Decimal('60.00')

    def __init__(self, repository: Optional[OrderRepository]=None, ecpay_gateway: Optional[ECPayGateway]=None):
        self.repository = repository or DjangoOrderRepository()
        self.ecpay_gateway = ecpay_gateway or ECPayMockAdapter()

    def create_order_from_cart(self, user) -> Dict[str, Any]:
        try:
            with transaction.atomic():
                cart = self.repository.get_cart_for_update(user)
                if not cart:
                    raise ValueError('購物車不存在')
                cart_items = list(self.repository.get_cart_items_for_update(cart))
                if not cart_items:
                    raise ValueError('購物車是空的，無法結帳')
                total_product_amount = Decimal('0.00')
                for cart_item in cart_items:
                    if cart_item.quantity <= 0:
                        raise ValueError('購物車商品數量必須大於 0')
                    product = cart_item.product
                    if product.is_deleted:
                        raise ValueError(f'商品「{product.name}」已下架')
                    if product.stock < cart_item.quantity:
                        raise ValueError(f'商品「{product.name}」庫存不足，目前庫存：{product.stock}')
                    total_product_amount += cart_item.price * cart_item.quantity
                total_amount = total_product_amount + self.SHIPPING_FEE
                order = self.repository.create_order(user=user, shipping_fee=self.SHIPPING_FEE, total_amount=total_amount, status='pending_payment', payment_method='')
                for cart_item in cart_items:
                    product = cart_item.product
                    self.repository.create_order_item(order=order, product=product, name=product.name, quantity=cart_item.quantity, price=cart_item.price)
                    new_stock = product.stock - cart_item.quantity
                    new_reserved_stock = product.reserved_stock + cart_item.quantity
                    self.repository.save_product_stock(product, stock=new_stock, reserved_stock=new_reserved_stock)
                    self.repository.create_inventory_reservation(order=order, product=product, quantity=cart_item.quantity, status='reserved')
                self.repository.clear_cart_items(cart)
                return {'success': True, 'stage': 1, 'order_number': order.order_number, 'status': order.status, 'total_amount': str(order.total_amount)}
        except ValueError:
            raise
        except Exception as exc:
            logger.exception('[OrderService.create_order_from_cart] 建立 Order 失敗')
            raise RuntimeError(f'建立訂單失敗：{exc}') from exc

    def process_existing_order_checkout(self, user, payload) -> Dict[str, Any]:
        if not payload.order_number:
            raise ValueError('第二階段缺少 order_number')
        if not payload.receiver_name:
            raise ValueError('缺少 receiver_name')
        if not payload.receiver_phone:
            raise ValueError('缺少 receiver_phone')
        if not payload.receiver_address:
            raise ValueError('缺少 receiver_address')
        if payload.payment_method not in ('ATM', 'COD'):
            raise ValueError('付款方式必須是 ATM 或 COD')
        try:
            with transaction.atomic():
                logger.warning('[DEBUG checkout] user_id=%s, payload.order_number=%r', user.id, payload.order_number)
                order = Order.objects.select_for_update().filter(order_number=payload.order_number, user=user).first()
                if not order:
                    raise ValueError('找不到訂單，或訂單不屬於目前使用者')
                if order.status == 'expired':
                    raise ValueError('此訂單已逾期未付款，無法再付款，請重新下單')
                if order.status != 'pending_payment':
                    raise ValueError(f'目前訂單狀態為 {order.status}，無法再次進行付款設定')
                order.receiver_name = payload.receiver_name
                order.receiver_phone = payload.receiver_phone
                order.receiver_address = payload.receiver_address
                order.payment_method = payload.payment_method
                order.remark = payload.remark or ''
                order.save(update_fields=['receiver_name', 'receiver_phone', 'receiver_address', 'payment_method', 'remark', 'updated_at'])
            return {'success': True, 'order_number': order.order_number, 'status': order.status, 'payment_method': order.payment_method, 'total_amount': str(order.total_amount), 'message': '訂單資料更新成功。'}
        except ValueError:
            raise
        except Exception as exc:
            logger.exception('[OrderService.process_existing_order_checkout] 更新 Order 失敗')
            raise RuntimeError(f'更新訂單失敗：{exc}') from exc

    def prepare_ecpay_atm_checkout(self, user, order_number: str) -> Dict[str, Any]:
        if not order_number:
            raise ValueError('缺少 order_number')
        try:
            order = Order.objects.filter(order_number=order_number, user=user).first()
            if not order:
                raise ValueError('找不到訂單，或訂單不屬於目前使用者')
            if order.status != 'pending_payment':
                raise ValueError(f'目前訂單狀態為 {order.status}，無法進行 ATM 付款')
            if order.payment_method != 'ATM':
                raise ValueError('目前訂單付款方式不是 ATM')
            items = order.items.select_related('product').all()
            item_names = '#'.join((item.product.name for item in items))
            if not item_names:
                item_names = f'訂單 {order.order_number}'
            payload = self._build_ecpay_atm_payload(order)
            payload.update({'merchant_id': '2000132', 'merchant_trade_date': timezone.localtime(order.created_at).strftime('%Y-%m-%d %H:%M:%S'), 'user_id': user.id, 'receiver_name': order.receiver_name or '', 'trade_desc': order.remark or '購買商品', 'item_name': item_names, 'status': order.status})
            logger.info('[OrderService.prepare_ecpay_atm_checkout] Order=%s ECPay payload 建立成功', order.order_number)
            return payload
        except ValueError:
            raise
        except Exception as exc:
            logger.exception('[OrderService.prepare_ecpay_atm_checkout] 建立 ECPay ATM payload 失敗')
            raise RuntimeError('建立 ECPay ATM 付款資料失敗') from exc

    def prepare_ecpay_checkout(self, user, order_number: str) -> Dict[str, Any]:
        order = Order.objects.filter(order_number=order_number, user=user).first()
        if not order:
            raise ValueError('找不到訂單，或訂單不屬於目前使用者')
        if order.payment_method == 'COD':
            return self.prepare_ecpay_cod_checkout(user=user, order_number=order_number)
        return self.prepare_ecpay_atm_checkout(user=user, order_number=order_number)

    def prepare_ecpay_cod_checkout(self, user, order_number: str) -> Dict[str, Any]:
        order = Order.objects.filter(order_number=order_number, user=user).first()
        if not order:
            raise ValueError('找不到訂單，或訂單不屬於目前使用者')
        if order.status != 'pending_payment':
            raise ValueError(f'目前訂單狀態為 {order.status}，無法進行超商取貨付款')
        if order.payment_method != 'COD':
            raise ValueError('目前訂單付款方式不是 COD')
        item_names = '#'.join(order.items.values_list('name', flat=True)) or f'訂單 {order.order_number}'
        store_base_url = (getattr(settings, 'HF_SPACE_E_COMMERCE_URL', '') or '').rstrip('/')
        return {'merchant_trade_no': order.order_number, 'merchant_trade_date': timezone.localtime(order.created_at).strftime('%Y-%m-%d %H:%M:%S'), 'user_id': user.id, 'trade_amt': str(order.total_amount), 'trade_desc': order.remark or '購買商品', 'item_name': item_names, 'payment_type': 'aio', 'choose_payment': 'COD', 'payment_method': 'COD', 'receiver_name': order.receiver_name or '', 'receiver_cell_phone': order.receiver_phone or '', 'receiver_address': order.receiver_address or '', 'ReturnURL': f'{store_base_url}/commerce_shop/cod_payment_notify/', 'OrderResultURL': f'{store_base_url}/commerce_shop/purchased_products/', 'action_url': f'{settings.HF_SPACE_ECPAY_MOCK_URL}/cod_gateway/cod_checkout/'}

    @classmethod
    def checkout(cls, user, cart):
        with transaction.atomic():
            cart_items = cart.items.select_related('product').all()
            items_total = Decimal('0.00')
            for item in cart_items:
                if item.product.stock < item.quantity:
                    raise ValueError(f'商品 {item.product.name} 庫存不足，目前僅剩 {item.product.stock} 件。')
                items_total += item.price * item.quantity
            shipping_fee = Decimal('60.00')
            total_amount = items_total + shipping_fee
            order_number = f'ORD-{uuid.uuid4().hex[:12].upper()}'
            order = Order.objects.create(order_number=order_number, user=user, shipping_fee=shipping_fee, total_amount=total_amount, status='pending_payment', shipping_status='pending')
            for item in cart_items:
                OrderItem.objects.create(order=order, product=item.product, name=item.product.name, quantity=item.quantity, price=item.price)
                product = item.product
                product.stock -= item.quantity
                product.reserved_stock += item.quantity
                product.save()
                InventoryReservation.objects.create(order=order, product=product, quantity=item.quantity, status='reserved')
            cart_items.delete()
            return order

    def _build_ecpay_atm_payload(self, order) -> Dict[str, Any]:
        try:
            store_base_url = (getattr(settings, 'HF_SPACE_E_COMMERCE_URL', '') or '').rstrip('/')
            payload = {'merchant_trade_no': order.order_number, 'trade_amt': str(order.total_amount), 'payment_type': 'aio', 'choose_payment': 'ATM', 'payment_method': 'ATM', 'ReturnURL': f'{store_base_url}/commerce_shop/atm_payment_notify/', 'OrderResultURL': f'{store_base_url}/commerce_shop/payment_ok/', 'action_url': f'{settings.HF_SPACE_ECPAY_MOCK_URL}/gateway/ecpay_gateway_checkout/'}
            return payload
        except Exception as exc:
            logger.exception('[OrderService._build_ecpay_atm_payload] 建立 ECPay payload 失敗')
            raise RuntimeError('建立 ECPay ATM 付款資料失敗') from exc

    def mark_order_paid(self, order):
        try:
            with transaction.atomic():
                locked_order = self.repository.get_order_by_pk_for_update(order_pk=order.pk)
                if not locked_order:
                    raise ValueError('找不到要更新付款狀態的訂單')
                if locked_order.status == 'paid':
                    return locked_order
                if locked_order.status in ('cancelled', 'expired'):
                    raise ValueError(f'訂單目前狀態為 {locked_order.status}，不能再標記為 paid')
                reservations = list(self.repository.get_reservations_for_update(locked_order))
                for reservation in reservations:
                    if reservation.status != 'reserved':
                        continue
                    product = reservation.product
                    new_reserved_stock = max(0, product.reserved_stock - reservation.quantity)
                    self.repository.save_product_reserved_stock(product, reserved_stock=new_reserved_stock)
                    self.repository.save_reservation(reservation, status='committed')
                self.repository.save_order_status(locked_order, status='paid')
                return locked_order
        except ValueError:
            raise
        except Exception as exc:
            logger.exception('[OrderService.mark_order_paid] Order paid 更新失敗')
            raise RuntimeError('訂單付款成功處理失敗') from exc

    def release_order_inventory(self, order, order_status='expired'):
        if order_status not in ('expired', 'cancelled'):
            raise ValueError('release_order_inventory 只能使用 expired / cancelled')
        try:
            with transaction.atomic():
                locked_order = self.repository.get_order_by_pk_for_update(order_pk=order.pk)
                if not locked_order:
                    raise ValueError('找不到要釋放庫存的訂單')
                if locked_order.status in ('expired', 'cancelled'):
                    return locked_order
                if locked_order.status == 'paid':
                    raise ValueError('已付款訂單不能釋放庫存')
                reservations = list(self.repository.get_reservations_for_update(locked_order))
                for reservation in reservations:
                    if reservation.status != 'reserved':
                        continue
                    product = reservation.product
                    new_stock = product.stock + reservation.quantity
                    new_reserved_stock = max(0, product.reserved_stock - reservation.quantity)
                    self.repository.save_product_inventory(product, stock=new_stock, reserved_stock=new_reserved_stock)
                    self.repository.save_reservation(reservation, status='released')
                self.repository.save_order_status(locked_order, status=order_status)
                return locked_order
        except ValueError:
            raise
        except Exception as exc:
            logger.exception('[OrderService.release_order_inventory] 庫存釋放失敗')
            raise RuntimeError('庫存釋放失敗') from exc
```

### 📄 `E_commerce/commerce_shop/services/payment_service.py`

#### `PaymentService`（class，原檔第 29–1915 行）
> Payment Business Service。

```python
class PaymentService:
    STATUS_MAP = {'pending': 'pending', 'atm_created': 'pending', 'paid': 'success', 'success': 'success', 'atm_paid': 'success', 'failed': 'failed', 'atm_failed': 'failed', 'expired': 'expired', 'atm_expired': 'expired', 'cancelled': 'cancelled', 'atm_cancelled': 'cancelled'}
    COD_STATUS_MAP = {'cod_confirmed': ('pending', 'pending_payment'), 'cod_created': ('pending', 'pending_payment'), 'cod_shipped': ('pending', 'shipped'), 'cod_paid': ('success', 'paid'), 'cod_failed': ('failed', 'pending_payment'), 'cod_expired': ('expired', 'expired')}

    def __init__(self, ecpay_gateway=None):
        self.ecpay_gateway = ecpay_gateway or ECPayMockAdapter()

    def create_payment(self, *, user, order_number: str, payment_method: str) -> Dict[str, Any]:
        if payment_method != 'ATM':
            raise ValueError('目前 PaymentService 只支援 ATM')
        if not order_number:
            raise ValueError('缺少 order_number')
        order = Order.objects.filter(order_number=order_number, user=user).first()
        if not order:
            raise ValueError('找不到訂單，或訂單不屬於目前使用者')
        if order.status != 'pending_payment':
            raise ValueError(f'目前訂單狀態為 {order.status}，無法建立 ATM Payment')
        if order.payment_method != 'ATM':
            raise ValueError('Order 的 payment_method 不是 ATM')
        item_names = ','.join(order.items.values_list('name', flat=True))
        if not item_names:
            item_names = '購買商品'
        if order.created_at:
            merchant_trade_date = timezone.localtime(order.created_at).strftime('%Y-%m-%d %H:%M:%S')
        else:
            merchant_trade_date = timezone.localtime().strftime('%Y-%m-%d %H:%M:%S')
        merchant_id = getattr(settings, 'ECPAY_MERCHANT_ID', '2000132')
        gateway_payload = {'merchant_id': merchant_id, 'merchant_trade_no': order.order_number, 'merchant_trade_date': merchant_trade_date, 'trade_amt': str(order.total_amount), 'trade_desc': order.remark or '購買商品', 'item_name': item_names, 'payment_type': 'aio', 'choose_payment': 'ATM', 'user_id': str(order.user_id), 'receiver_name': order.receiver_name or ''}
        gateway_payload['CheckMacValue'] = self._generate_check_mac_value(gateway_payload)
        try:
            atm_result = self.ecpay_gateway.create_atm_payment(gateway_payload)
            logger.info('ECPay Gateway 原始回應: %s', atm_result)
        except ValueError:
            raise
        except RuntimeError:
            raise
        except Exception as exc:
            logger.exception('ECPay ATM Gateway 呼叫失敗')
            raise RuntimeError('ATM 付款建立失敗') from exc
        if not isinstance(atm_result, dict):
            raise RuntimeError('ECPay Gateway 回傳格式錯誤')
        gateway_success = atm_result.get('success')
        if gateway_success is None:
            gateway_status = atm_result.get('status')
            gateway_success = gateway_status is True or gateway_status == 'success'
        if not gateway_success:
            raise RuntimeError(atm_result.get('message', 'ATM 付款建立失敗'))
        payment_data = atm_result.get('payment')
        if not isinstance(payment_data, dict):
            payment_data = atm_result
        response_merchant_trade_no = payment_data.get('merchant_trade_no')
        if not response_merchant_trade_no:
            raise RuntimeError('ECPay Gateway 回應缺少 merchant_trade_no')
        if str(response_merchant_trade_no) != str(order.order_number):
            raise RuntimeError('ECPay Gateway merchant_trade_no 不一致')
        bank_code = payment_data.get('bank_code')
        v_account = payment_data.get('v_account')
        expire_date = payment_data.get('expire_date')
        if not bank_code:
            raise RuntimeError('Bank Mock 沒有回傳 bank_code')
        if not v_account:
            raise RuntimeError('Bank Mock 沒有回傳 v_account')
        if not expire_date:
            raise RuntimeError('Bank Mock 沒有回傳 expire_date')
        expire_datetime = self._normalize_expire_date(expire_date)
        if expire_datetime <= timezone.now():
            raise RuntimeError('ATM 付款期限已經過期')
        provider_transaction_id = payment_data.get('trade_no') or atm_result.get('trade_no')
        if not provider_transaction_id:
            raise RuntimeError('ECPay Gateway 回應缺少 trade_no')
        atm_info_url = atm_result.get('atm_info_url')
        with transaction.atomic():
            payment = Payment.objects.filter(provider='ecpay', provider_transaction_id=provider_transaction_id).first()
            if payment is not None:
                if payment.order_id != order.id:
                    raise RuntimeError('ECPay trade_no 已經屬於其他訂單')
                payment.payment_method = 'ATM'
                payment.amount = order.total_amount
                payment.status = 'pending'
                payment.bank_code = str(bank_code)
                payment.v_account = str(v_account)
                payment.expire_date = expire_datetime
                payment.payment_url = atm_info_url or ''
                payment.response_data = atm_result
                payment.save(update_fields=['payment_method', 'amount', 'status', 'bank_code', 'v_account', 'expire_date', 'payment_url', 'response_data', 'updated_at'])
            else:
                payment = Payment.objects.create(provider='ecpay', order=order, payment_method='ATM', amount=order.total_amount, status='pending', provider_transaction_id=str(provider_transaction_id), payment_url=atm_info_url or '', bank_code=str(bank_code), v_account=str(v_account), expire_date=expire_datetime, paid_at=None, response_data=atm_result)
        return {'payment_number': str(payment.payment_number), 'provider': payment.provider, 'provider_transaction_id': payment.provider_transaction_id, 'payment_method': payment.payment_method, 'amount': str(payment.amount), 'status': payment.status, 'bank_code': payment.bank_code, 'v_account': payment.v_account, 'expire_date': payment.expire_date.isoformat() if payment.expire_date else None, 'payment_url': payment.payment_url, 'atm_info_url': payment.payment_url, 'response_data': payment.response_data}

    def _generate_check_mac_value(self, payload: Dict[str, Any]) -> str:
        from util.ChkMacVal import generate_check_mac_value
        payload_for_mac = dict(payload)
        payload_for_mac.pop('CheckMacValue', None)
        hash_key = getattr(settings, 'ECPAY_HASH_KEY', '')
        hash_iv = getattr(settings, 'ECPAY_HASH_IV', '')
        if not hash_key:
            raise RuntimeError('未設定 ECPAY_HASH_KEY')
        if not hash_iv:
            raise RuntimeError('未設定 ECPAY_HASH_IV')
        return generate_check_mac_value(payload_for_mac, hash_key, hash_iv)

    def _normalize_expire_date(self, expire_date):
        if isinstance(expire_date, datetime):
            value = expire_date
        else:
            value = parse_datetime(str(expire_date))
            if value is None:
                raise ValueError('expire_date 格式錯誤')
        if timezone.is_naive(value):
            value = timezone.make_aware(value, timezone.get_current_timezone())
        return value

    def handle_cod_callback(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError('callback payload 必須是 dict')
        merchant_trade_no = payload.get('merchant_trade_no')
        callback_status = str(payload.get('status') or '').lower()
        trade_amt = payload.get('trade_amt')
        provider_transaction_id = payload.get('provider_transaction_id') or payload.get('trade_no')
        if not merchant_trade_no:
            raise ValueError('callback 缺少 merchant_trade_no')
        if callback_status not in self.COD_STATUS_MAP:
            raise ValueError(f'不支援的 COD 狀態：{callback_status}')
        if trade_amt in (None, ''):
            raise ValueError('callback 缺少 trade_amt')
        if not provider_transaction_id:
            raise ValueError('callback 缺少 provider_transaction_id')
        try:
            callback_amount = Decimal(str(trade_amt))
        except Exception as exc:
            raise ValueError('callback trade_amt 格式錯誤') from exc
        payment_status, target_order_status = self.COD_STATUS_MAP[callback_status]
        with transaction.atomic():
            order = Order.objects.select_for_update().filter(order_number=merchant_trade_no).first()
            if not order:
                raise ValueError('找不到 callback 對應的 Order')
            if order.payment_method != 'COD':
                raise ValueError('callback 對應的 Order 並非 COD')
            if callback_amount != order.total_amount:
                raise ValueError('callback 付款金額與訂單金額不一致')
            if order.status not in ('pending_payment', 'paid', 'shipped') and (not (order.status == 'expired' and str(payload.get('simulate', '')) == '1')):
                raise ValueError(f'目前訂單狀態為 {order.status}，無法更新 COD 狀態')
            payment = Payment.objects.select_for_update().filter(provider='ecpay', provider_transaction_id=str(provider_transaction_id)).first()
            payment_fields = {'payment_method': 'COD', 'amount': order.total_amount, 'status': payment_status, 'response_data': payload, 'paid_at': timezone.now() if payment_status == 'success' else None}
            if payment is None:
                payment = Payment.objects.create(provider='ecpay', order=order, provider_transaction_id=str(provider_transaction_id), payment_url='', **payment_fields)
            else:
                if payment.order_id != order.id:
                    raise ValueError('trade_no 已經屬於其他訂單')
                for field, value in payment_fields.items():
                    setattr(payment, field, value)
                payment.save(update_fields=list(payment_fields.keys()) + ['updated_at'])
            if order.status == 'expired' and target_order_status != 'expired':
                self._re_reserve_inventory(order)
            if target_order_status == 'paid' and order.status != 'paid':
                self._commit_inventory(order)
            elif order.status == 'paid' and target_order_status != 'paid':
                self._recommit_to_reserved(order)
            if target_order_status == 'expired':
                self._release_inventory(order)
            order_update_fields = ['status', 'updated_at']
            order.status = target_order_status
            if payload.get('cvs_store_name'):
                payment.cvs_store_name = str(payload['cvs_store_name'])
                payment.cvs_store_address = str(payload.get('cvs_store_address', ''))
                payment.save(update_fields=['cvs_store_name', 'cvs_store_address', 'updated_at'])
            order.save(update_fields=order_update_fields)
        return {'success': True, 'merchant_trade_no': order.order_number, 'payment_number': str(payment.payment_number), 'payment_status': payment.status, 'order_status': order.status, 'message': 'COD 狀態更新成功。'}

    def handle_atm_callback(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError('callback payload 必須是 dict')
        merchant_trade_no = payload.get('merchant_trade_no')
        bank_code = payload.get('bank_code')
        v_account = payload.get('v_account')
        expire_date = payload.get('expire_date')
        trade_amt = payload.get('trade_amt')
        callback_status = payload.get('payment_status') or payload.get('status') or 'atm_created'
        provider_transaction_id = payload.get('provider_transaction_id') or payload.get('trade_no')
        if not merchant_trade_no:
            raise ValueError('callback 缺少 merchant_trade_no')
        if not bank_code:
            raise ValueError('callback 缺少 bank_code')
        if not v_account:
            raise ValueError('callback 缺少 v_account')
        if not expire_date:
            raise ValueError('callback 缺少 expire_date')
        if trade_amt in (None, ''):
            raise ValueError('callback 缺少 trade_amt')
        if not provider_transaction_id:
            raise ValueError('callback 缺少 provider_transaction_id')
        payment_status = self.STATUS_MAP.get(str(callback_status).lower())
        if payment_status is None:
            raise ValueError(f'不支援的付款狀態：{callback_status}')
        try:
            callback_amount = Decimal(str(trade_amt))
        except (TypeError, ValueError) as exc:
            raise ValueError('callback trade_amt 格式錯誤') from exc
        expire_datetime = self._normalize_expire_date(expire_date)
        with transaction.atomic():
            order = Order.objects.select_for_update().filter(order_number=merchant_trade_no).first()
            if not order:
                raise ValueError('找不到 callback 對應的 Order')
            if order.payment_method != 'ATM':
                raise ValueError('callback 對應的 Order 並非 ATM')
            if order.status == 'expired' and str(payload.get('simulate', '')) != '1':
                raise ValueError('訂單已逾期，無法更新 ATM 付款狀態')
            if order.status == 'cancelled':
                raise ValueError('訂單已取消，無法更新 ATM 付款狀態')
            if callback_amount != order.total_amount:
                raise ValueError('callback 付款金額與訂單金額不一致')
            payment = Payment.objects.select_for_update().filter(provider='ecpay', provider_transaction_id=str(provider_transaction_id)).first()
            if payment is None:
                payment = Payment.objects.create(provider='ecpay', order=order, payment_method='ATM', amount=order.total_amount, status=payment_status, provider_transaction_id=str(provider_transaction_id), payment_url=payload.get('atm_info_url', '') or '', bank_code=str(bank_code), v_account=str(v_account), expire_date=expire_datetime, paid_at=None, response_data=payload)
                logger.info('Store Payment 建立成功：merchant_trade_no=%s, provider_transaction_id=%s', merchant_trade_no, provider_transaction_id)
            else:
                if payment.order_id != order.id:
                    raise ValueError('ECPay trade_no 已經屬於其他訂單')
                payment.payment_method = 'ATM'
                payment.amount = order.total_amount
                payment.status = payment_status
                payment.bank_code = str(bank_code)
                payment.v_account = str(v_account)
                payment.expire_date = expire_datetime
                payment.payment_url = payload.get('atm_info_url', payment.payment_url) or payment.payment_url or ''
                payment.response_data = payload
                if payment_status == 'success':
                    payment.paid_at = timezone.now()
                elif payment_status in ('failed', 'expired'):
                    payment.paid_at = None
                payment.save(update_fields=['payment_method', 'amount', 'status', 'bank_code', 'v_account', 'expire_date', 'payment_url', 'response_data', 'paid_at', 'updated_at'])
                logger.info('Store Payment 已存在，更新既有 Payment：merchant_trade_no=%s, provider_transaction_id=%s', merchant_trade_no, provider_transaction_id)
            if payment_status == 'success':
                if order.status == 'expired':
                    self._re_reserve_inventory(order)
                if order.status != 'paid':
                    self._commit_inventory(order)
                order.status = 'paid'
                order.save(update_fields=['status', 'updated_at'])
            elif payment_status == 'expired':
                if order.status == 'shipped':
                    raise ValueError('訂單已出貨，無法改為逾期未付款')
                if order.status == 'paid':
                    self._recommit_to_reserved(order)
                self._release_inventory(order)
                order.status = 'expired'
                order.save(update_fields=['status', 'updated_at'])
            elif payment_status == 'failed' and order.status in ('paid', 'expired'):
                if order.status == 'expired':
                    self._re_reserve_inventory(order)
                else:
                    self._recommit_to_reserved(order)
                order.status = 'pending_payment'
                order.save(update_fields=['status', 'updated_at'])
        return {'success': True, 'merchant_trade_no': order.order_number, 'payment_number': str(payment.payment_number), 'provider_transaction_id': payment.provider_transaction_id, 'payment_status': payment.status, 'order_status': order.status, 'bank_code': payment.bank_code, 'v_account': payment.v_account, 'expire_date': payment.expire_date.isoformat() if payment.expire_date else None, 'atm_info_url': payment.payment_url, 'message': 'ATM 付款資訊建立成功，Store Payment 已建立。'}

    def _commit_inventory(self, order: Order) -> None:
        reservations = InventoryReservation.objects.select_for_update().select_related('product').filter(order=order, status='reserved')
        for reservation in reservations:
            product = reservation.product
            product.reserved_stock = max(product.reserved_stock - reservation.quantity, 0)
            product.save(update_fields=['reserved_stock'])
            reservation.status = 'committed'
            reservation.save(update_fields=['status', 'updated_at'])

    def _recommit_to_reserved(self, order: Order) -> None:
        reservations = InventoryReservation.objects.select_for_update().select_related('product').filter(order=order, status='committed')
        for reservation in reservations:
            product = reservation.product
            product.reserved_stock += reservation.quantity
            product.save(update_fields=['reserved_stock'])
            reservation.status = 'reserved'
            reservation.save(update_fields=['status', 'updated_at'])

    def cancel_order(self, order: Order) -> None:
        if order.status not in ('pending_payment', 'failed'):
            raise ValueError('只有待付款或付款失敗的訂單可以取消')
        atm_payment = order.payments.filter(payment_method='ATM', status__in=['pending', 'failed']).first()
        if order.payment_method == 'COD':
            self.ecpay_gateway.cancel_payment(order.order_number, 'COD')
        elif atm_payment is not None:
            self.ecpay_gateway.cancel_payment(order.order_number, 'ATM')
        with transaction.atomic():
            self._release_inventory(order)
            order.status = 'cancelled'
            order.save(update_fields=['status', 'updated_at'])
            latest_payment = order.payments.order_by('-created_at').first()
            if latest_payment is not None:
                latest_payment.status = 'cancelled'
                latest_payment.save(update_fields=['status', 'updated_at'])

    def _release_inventory(self, order: Order) -> None:
        reservations = InventoryReservation.objects.select_related('product').filter(order=order, status='reserved')
        for reservation in reservations:
            product = reservation.product
            product.stock += reservation.quantity
            product.reserved_stock = max(product.reserved_stock - reservation.quantity, 0)
            product.save(update_fields=['stock', 'reserved_stock'])
            reservation.status = 'released'
            reservation.save(update_fields=['status'])

    def _re_reserve_inventory(self, order: Order) -> None:
        reservations = InventoryReservation.objects.select_for_update().select_related('product').filter(order=order, status='released')
        for reservation in reservations:
            product = reservation.product
            if product.stock < reservation.quantity:
                raise ValueError(f'商品「{product.name}」庫存不足，無法還原逾期訂單')
            product.stock -= reservation.quantity
            product.reserved_stock += reservation.quantity
            product.save(update_fields=['stock', 'reserved_stock'])
            reservation.status = 'reserved'
            reservation.save(update_fields=['status', 'updated_at'])
```

### 📄 `E_commerce/commerce_shop/services/order_query_service.py`

#### `OrderQueryService`（class，原檔第 18–140 行）
> 【新增】

```python
class OrderQueryService:
    PAYMENT_STATUS_TEXT = {'cod_confirmed': '待出貨，貨到超商時付現', 'cod_created': '待出貨，貨到超商時付現', 'cod_shipped': '配送中,待取貨付款', 'cod_paid': '已取貨付款', 'cod_failed': '取貨失敗未付款', 'cod_expired': '逾期未付款', 'atm_created': '待付款', 'paid': '已付款', 'failed': '付款失敗', 'expired': '逾期未付款', 'pending': '處理中', 'success': '已付款', 'cancelled': '已取消'}

    @classmethod
    def get_payment_status_text(cls, order):
        payments = getattr(order, 'all_payments', [])
        if not payments:
            return ''
        payment = payments[0]
        data = payment.response_data if isinstance(payment.response_data, dict) else {}
        return cls.PAYMENT_STATUS_TEXT.get(str(data.get('status'))) or cls.PAYMENT_STATUS_TEXT.get(payment.status, '')

    @staticmethod
    def get_user_orders(user):
        try:
            orders = Order.objects.filter(user=user).prefetch_related('items__product', Prefetch('payments', queryset=Payment.objects.filter(payment_method='ATM').order_by('-created_at'), to_attr='atm_payments'), Prefetch('payments', queryset=Payment.objects.order_by('-created_at'), to_attr='all_payments')).order_by('-created_at')
            return list(orders)
        except Exception as exc:
            logger.exception('[OrderQueryService.get_user_orders] 讀取訂單失敗')
            raise RuntimeError('讀取訂單失敗') from exc
```

<a id="layer-6"></a>

## 6. 介面層 Interfaces（抽象 ABC）

Service 只依賴這些抽象，不知道 httpx / ORM。

### 📄 `E_commerce/commerce_shop/interfaces/ecpay_gateway.py`

#### `ECPayGateway`（class，原檔第 10–80 行）
> ECPay Gateway Interface。

```python
class ECPayGateway(ABC):

    @abstractmethod
    def create_atm_payment(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def cancel_payment(self, merchant_trade_no: str, payment_method: str='ATM') -> Dict[str, Any]:
        pass

    @abstractmethod
    def query_payment(self, merchant_trade_no: str) -> Dict[str, Any]:
        raise NotImplementedError
```

### 📄 `E_commerce/commerce_shop/interfaces/order_repository.py`

#### `OrderRepository`（class，原檔第 9–296 行）
> Order Repository Interface。

```python
class OrderRepository(ABC):

    @abstractmethod
    def get_cart_for_update(self, user):
        raise NotImplementedError

    @abstractmethod
    def get_cart_items_for_update(self, cart):
        raise NotImplementedError

    @abstractmethod
    def clear_cart_items(self, cart) -> None:
        raise NotImplementedError

    @abstractmethod
    def create_order(self, *, user, shipping_fee, total_amount, status, payment_method):
        raise NotImplementedError

    @abstractmethod
    def create_order_item(self, *, order, product, name, quantity, price):
        raise NotImplementedError

    @abstractmethod
    def save_product_stock(self, product, *, stock, reserved_stock) -> None:
        raise NotImplementedError

    @abstractmethod
    def create_inventory_reservation(self, *, order, product, quantity, status):
        raise NotImplementedError

    @abstractmethod
    def get_order_for_update(self, *, user, order_number):
        raise NotImplementedError

    @abstractmethod
    def save_order_checkout_data(self, order, *, receiver_name, receiver_phone, receiver_address, payment_method, remark) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_order_by_pk_for_update(self, *, order_pk):
        raise NotImplementedError

    @abstractmethod
    def get_reservations_for_update(self, order):
        raise NotImplementedError

    @abstractmethod
    def save_reservation(self, reservation, *, status) -> None:
        raise NotImplementedError

    @abstractmethod
    def save_product_reserved_stock(self, product, *, reserved_stock) -> None:
        raise NotImplementedError

    @abstractmethod
    def save_product_inventory(self, product, *, stock, reserved_stock) -> None:
        raise NotImplementedError

    @abstractmethod
    def save_order_status(self, order, *, status) -> None:
        raise NotImplementedError
```

### 📄 `E_commerce/commerce_shop/interfaces/payment_repository.py`

#### `PaymentRepository`（class，原檔第 9–133 行）
> Payment Repository Interface。

```python
class PaymentRepository(ABC):

    @abstractmethod
    def get_order_for_update(self, merchant_trade_no: str):
        raise NotImplementedError

    @abstractmethod
    def get_payment_by_provider_transaction_id_for_update(self, provider_transaction_id: str):
        raise NotImplementedError

    @abstractmethod
    def get_payment_for_update(self, *, order, payment_method: str, v_account: str):
        raise NotImplementedError

    @abstractmethod
    def create_payment(self, *, order, provider: str, payment_method: str, amount, status: str, bank_code: Optional[str], v_account: Optional[str], expire_date, provider_transaction_id: Optional[str], response_data: Optional[Dict[str, Any]]):
        raise NotImplementedError

    @abstractmethod
    def save_payment(self, payment, *, provider_transaction_id: Optional[str], status: str, bank_code: Optional[str], v_account: Optional[str], expire_date, response_data: Optional[Dict[str, Any]]):
        raise NotImplementedError
```

<a id="layer-7"></a>

## 7. 轉接層 Adapters（httpx / ORM）

呼叫 httpx 的地方；ORM repository 目前只有 OrderService 用 DjangoOrderRepository，PaymentService 已不使用 PaymentRepository。

### 📄 `E_commerce/commerce_shop/adapters/ecpay_mock_adapter.py`

#### `ECPayMockAdapter`（class，原檔第 24–619 行）
> Store → ECPay Mock HTTPX Adapter。

```python
class ECPayMockAdapter(ECPayGateway):

    def __init__(self, base_url: Optional[str]=None, checkout_path: Optional[str]=None, query_path: Optional[str]=None, timeout: Optional[float]=None):
        self.base_url = (base_url or getattr(settings, 'HF_SPACE_ECPAY_MOCK_URL', '') or getattr(settings, 'ECPAY_MOCK_URL', '')).rstrip('/')
        if not self.base_url:
            raise RuntimeError('缺少 ECPay Mock URL 設定')
        self.checkout_path = checkout_path or '/gateway/ecpay_gateway_checkout/'
        self.query_path = query_path or '/gateway/payment_query/'
        self.timeout = timeout if timeout is not None else 10.0

    def _build_url(self, path: str) -> str:
        if not path.startswith('/'):
            path = f'/{path}'
        return f'{self.base_url}{path}'

    def _sign_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError('ECPay payload 必須是 dict')
        signed_payload = dict(payload)
        signed_payload.pop('CheckMacValue', None)
        signed_payload.pop('check_mac_value', None)
        hash_key = getattr(settings, 'ECPAY_HASH_KEY', '')
        hash_iv = getattr(settings, 'ECPAY_HASH_IV', '')
        if not hash_key or not hash_iv:
            raise RuntimeError('缺少 ECPAY_HASH_KEY / ECPAY_HASH_IV')
        check_mac_value = generate_check_mac_value(signed_payload, hash_key, hash_iv)
        signed_payload['CheckMacValue'] = check_mac_value
        return signed_payload

    def _post_json(self, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            response = httpx.post(url, json=payload, timeout=self.timeout)
        except httpx.TimeoutException as exc:
            logger.exception('ECPay Mock request timeout')
            raise RuntimeError('ECPay Mock request timeout') from exc
        except httpx.RequestError as exc:
            logger.exception('ECPay Mock request error')
            raise RuntimeError(f'ECPay Mock request error：{exc}') from exc
        except Exception as exc:
            logger.exception('ECPay Mock HTTP request 未預期錯誤')
            raise RuntimeError('ECPay Mock HTTP request 失敗') from exc
        if not 200 <= response.status_code < 300:
            logger.error('ECPay Mock HTTP status=%s body=%s', response.status_code, response.text)
            raise RuntimeError(f'ECPay Mock HTTP status={response.status_code}')
        try:
            response_data = response.json()
        except ValueError as exc:
            logger.exception('ECPay Mock 回傳不是合法 JSON')
            raise RuntimeError('ECPay Mock 回傳資料不是合法 JSON') from exc
        if not isinstance(response_data, dict):
            raise RuntimeError('ECPay Mock JSON response 必須是 dict')
        return response_data

    def create_atm_payment(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError('ATM payment payload 必須是 dict')
        merchant_trade_no = payload.get('merchant_trade_no')
        if not merchant_trade_no:
            raise ValueError('缺少 merchant_trade_no')
        trade_amt_raw = payload.get('trade_amt')
        if trade_amt_raw is None or str(trade_amt_raw).strip() == '':
            raise ValueError('缺少 trade_amt')
        try:
            trade_amt = Decimal(str(trade_amt_raw))
        except Exception as exc:
            raise ValueError('trade_amt 格式錯誤') from exc
        if trade_amt <= 0:
            raise ValueError('trade_amt 必須大於 0')
        request_payload = dict(payload)
        request_payload['merchant_trade_no'] = str(merchant_trade_no)
        request_payload['trade_amt'] = str(trade_amt)
        request_payload['payment_type'] = 'aio'
        request_payload['choose_payment'] = 'ATM'
        request_payload['payment_method'] = 'ATM'
        signed_payload = self._sign_payload(request_payload)
        url = self._build_url(self.checkout_path)
        response_data = self._post_json(url, signed_payload)
        status_value = response_data.get('status')
        response_status = response_data.get('response_status')
        failure_values = {False, 'false', 'failed', 'error', 'failure'}
        if status_value in failure_values or str(status_value).lower() in failure_values or str(response_status).lower() in failure_values:
            logger.error('ECPay Mock 拒絕 ATM 請求：%s', response_data)
            raise RuntimeError('ECPay Mock 拒絕 ATM 付款請求')
        return {'success': True, 'status': 'accepted', 'merchant_trade_no': str(merchant_trade_no), 'gateway_response': response_data}

    def cancel_payment(self, merchant_trade_no: str, payment_method: str='ATM') -> Dict[str, Any]:
        if not merchant_trade_no:
            raise ValueError('merchant_trade_no 不可為空')
        payload = {'merchant_trade_no': str(merchant_trade_no)}
        signed_payload = self._sign_payload(payload)
        url = self._build_url('/cod_gateway/cod_cancel/' if payment_method == 'COD' else '/gateway/cancel_order/')
        response_data = self._post_json(url, signed_payload)
        if not response_data.get('status'):
            raise RuntimeError(f"ECPay Mock 取消失敗：{response_data.get('message') or '未知錯誤'}")
        return response_data

    def query_payment(self, merchant_trade_no: str) -> Dict[str, Any]:
        if not merchant_trade_no:
            raise ValueError('merchant_trade_no 不可為空')
        payload = {'merchant_trade_no': str(merchant_trade_no)}
        signed_payload = self._sign_payload(payload)
        url = self._build_url(self.query_path)
        return self._post_json(url, signed_payload)
```

### 📄 `E_commerce/commerce_shop/adapters/django_order_repository.py`

#### `DjangoOrderRepository`（class，原檔第 24–680 行）
> Django Order Repository。

```python
class DjangoOrderRepository(OrderRepository):

    def get_cart_for_update(self, user):
        try:
            return Cart.objects.select_for_update().filter(user=user).first()
        except Exception as exc:
            logger.exception('[DjangoOrderRepository] 取得 Cart 失敗')
            raise RuntimeError('取得購物車失敗') from exc

    def get_cart_items_for_update(self, cart):
        try:
            return list(cart.items.select_related('product').select_for_update())
        except Exception as exc:
            logger.exception('[DjangoOrderRepository] 取得 CartItem 失敗')
            raise RuntimeError('取得購物車商品失敗') from exc

    def clear_cart_items(self, cart) -> None:
        try:
            CartItem.objects.filter(cart=cart).delete()
        except Exception as exc:
            logger.exception('[DjangoOrderRepository] 清空 CartItem 失敗')
            raise RuntimeError('清空購物車失敗') from exc

    def create_order(self, *, user, shipping_fee, total_amount, status, payment_method):
        try:
            return Order.objects.create(user=user, shipping_fee=shipping_fee, total_amount=total_amount, status=status, payment_method=payment_method)
        except Exception as exc:
            logger.exception('[DjangoOrderRepository] 建立 Order 失敗')
            raise RuntimeError('建立訂單失敗') from exc

    def create_order_item(self, *, order, product, name, quantity, price):
        try:
            return OrderItem.objects.create(order=order, product=product, name=name, quantity=quantity, price=price)
        except Exception as exc:
            logger.exception('[DjangoOrderRepository] 建立 OrderItem 失敗')
            raise RuntimeError('建立訂單商品失敗') from exc

    def save_product_stock(self, product, *, stock, reserved_stock) -> None:
        try:
            product.stock = stock
            product.reserved_stock = reserved_stock
            product.save(update_fields=['stock', 'reserved_stock'])
        except Exception as exc:
            logger.exception('[DjangoOrderRepository] 更新 Product 庫存失敗')
            raise RuntimeError('更新商品庫存失敗') from exc

    def create_inventory_reservation(self, *, order, product, quantity, status):
        try:
            return InventoryReservation.objects.create(order=order, product=product, quantity=quantity, status=status)
        except Exception as exc:
            logger.exception('[DjangoOrderRepository] 建立 InventoryReservation 失敗')
            raise RuntimeError('建立庫存預約失敗') from exc

    def get_order_for_update(self, *, user, order_number):
        try:
            return Order.objects.select_for_update().filter(order_number=order_number, user=user).first()
        except Exception as exc:
            logger.exception('[DjangoOrderRepository] 取得指定 Order 失敗')
            raise RuntimeError('取得訂單失敗') from exc

    def save_order_checkout_data(self, order, *, receiver_name, receiver_phone, receiver_address, payment_method, remark) -> None:
        try:
            order.receiver_name = receiver_name
            order.receiver_phone = receiver_phone
            order.receiver_address = receiver_address
            order.payment_method = payment_method
            order.remark = remark
            order.save(update_fields=['receiver_name', 'receiver_phone', 'receiver_address', 'payment_method', 'remark', 'updated_at'])
        except Exception as exc:
            logger.exception('[DjangoOrderRepository] 更新 Order Checkout 資料失敗')
            raise RuntimeError('更新訂單收件資料失敗') from exc

    def get_order_by_pk_for_update(self, *, order_pk):
        try:
            return Order.objects.select_for_update().get(pk=order_pk)
        except Order.DoesNotExist as exc:
            raise ValueError('找不到指定訂單') from exc
        except Exception as exc:
            logger.exception('[DjangoOrderRepository] 鎖定 Order 失敗')
            raise RuntimeError('取得訂單失敗') from exc

    def get_reservations_for_update(self, order):
        try:
            return list(order.inventory_reservations.select_related('product').select_for_update())
        except Exception as exc:
            logger.exception('[DjangoOrderRepository] 取得 InventoryReservation 失敗')
            raise RuntimeError('取得庫存預約失敗') from exc

    def save_reservation(self, reservation, *, status) -> None:
        try:
            reservation.status = status
            reservation.save(update_fields=['status', 'updated_at'])
        except Exception as exc:
            logger.exception('[DjangoOrderRepository] 更新 Reservation 失敗')
            raise RuntimeError('更新庫存預約狀態失敗') from exc

    def save_product_reserved_stock(self, product, *, reserved_stock) -> None:
        try:
            product.reserved_stock = reserved_stock
            product.save(update_fields=['reserved_stock'])
        except Exception as exc:
            logger.exception('[DjangoOrderRepository] 更新 reserved_stock 失敗')
            raise RuntimeError('更新商品保留庫存失敗') from exc

    def save_product_inventory(self, product, *, stock, reserved_stock) -> None:
        try:
            product.stock = stock
            product.reserved_stock = reserved_stock
            product.save(update_fields=['stock', 'reserved_stock'])
        except Exception as exc:
            logger.exception('[DjangoOrderRepository] 更新商品庫存失敗')
            raise RuntimeError('更新商品庫存失敗') from exc

    def save_order_status(self, order, *, status) -> None:
        try:
            order.status = status
            order.save(update_fields=['status', 'updated_at'])
        except Exception as exc:
            logger.exception('[DjangoOrderRepository] 更新 Order 狀態失敗')
            raise RuntimeError('更新訂單狀態失敗') from exc
```

### 📄 `E_commerce/commerce_shop/adapters/django_payment_repository.py`

#### `DjangoPaymentRepository`（class，原檔第 22–292 行）
> Django ORM implementation。

```python
class DjangoPaymentRepository(PaymentRepository):

    def get_order_for_update(self, merchant_trade_no: str):
        if not merchant_trade_no:
            raise ValueError('merchant_trade_no 不可為空')
        try:
            order = Order.objects.select_for_update().filter(order_number=merchant_trade_no).first()
            return order
        except Exception as exc:
            logger.exception('PaymentRepository 取得 Order 失敗')
            raise RuntimeError('取得訂單失敗') from exc

    def get_payment_by_provider_transaction_id_for_update(self, provider_transaction_id: str):
        if not provider_transaction_id:
            return None
        try:
            return Payment.objects.select_for_update().filter(provider_transaction_id=provider_transaction_id).order_by('-created_at').first()
        except Exception as exc:
            logger.exception('依 provider_transaction_id 查詢 Payment 失敗')
            raise RuntimeError('查詢 Payment 失敗') from exc

    def get_payment_for_update(self, *, order, payment_method: str, v_account: str):
        try:
            return Payment.objects.select_for_update().filter(order=order, payment_method=payment_method, v_account=v_account).order_by('-created_at').first()
        except Exception as exc:
            logger.exception('依 Order + v_account 查詢 Payment 失敗')
            raise RuntimeError('查詢 Payment 失敗') from exc

    def create_payment(self, *, order, provider: str, payment_method: str, amount, status: str, bank_code: Optional[str], v_account: Optional[str], expire_date, provider_transaction_id: Optional[str], response_data: Optional[Dict[str, Any]]):
        try:
            return Payment.objects.create(order=order, provider=provider, payment_method=payment_method, amount=amount, status=status, bank_code=bank_code, v_account=v_account, expire_date=expire_date, provider_transaction_id=provider_transaction_id, response_data=response_data)
        except Exception as exc:
            logger.exception('建立 Payment 失敗')
            raise RuntimeError('建立 Payment 失敗') from exc

    def save_payment(self, payment, *, provider_transaction_id: Optional[str], status: str, bank_code: Optional[str], v_account: Optional[str], expire_date, response_data: Optional[Dict[str, Any]]):
        try:
            payment.provider_transaction_id = provider_transaction_id
            payment.status = status
            payment.bank_code = bank_code
            payment.v_account = v_account
            payment.expire_date = expire_date
            payment.response_data = response_data
            payment.save(update_fields=['provider_transaction_id', 'status', 'bank_code', 'v_account', 'expire_date', 'response_data', 'updated_at'])
            return payment
        except Exception as exc:
            logger.exception('更新 Payment 失敗')
            raise RuntimeError('更新 Payment 失敗') from exc
```
