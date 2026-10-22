# ecpay_mock（模擬金流）— 分層重要程式碼

> **閱讀說明**：本文件由原始碼自動擷取（AST），只保留「重要流程的程式碼」，已移除 docstring 與註解並重新排版（縮排、引號可能與原檔略有不同），僅供閱讀與理解架構；實際修改請以原始檔為準。每段標題附有原檔行號。
> 擷取來源：`E-Shop_Api_1012.zip`（2026-10-14 最新版）：含取消訂單、ATM 取消守衛、刪除同步、金額重算。

## 專案定位
模擬綠界金流閘道（Django + SQLite，HF Space）。兩個 app：
- `gateway`：ATM 虛擬帳號（會呼叫 Bank_site）
- `cod_gateway`：超商取貨付款 COD（**不經過 Bank**）

## 呼叫關係
```
E_commerce ──► gateway/views ──► ECPayService ──► ecpay_gateway(interface) ──► ECPayMockAdapter ──httpx──► Bank_site
                                      └─► store_payment_gateway ──► StorePaymentAdapter ──httpx──► E_commerce
E_commerce ──► cod_gateway/views ──► CODService ──► cod_store_gateway ──► CODStoreAdapter ──httpx──► E_commerce
```

## 共同規則
- 送出前簽 CheckMacValue、收到先驗證。
- **先 httpx 下游，成功後才寫自己的 DB**（取消流程中 COD 的 ecpay_mock 是鏈尾，直接寫）。
- COD 模擬動作帶 `simulate="1"`（簽進 CheckMacValue），E_commerce 才允許改動逾期單。

## 狀態
- `gateway.PaymentRequest.status`：atm_created / atm_paid / atm_failed / atm_expired / atm_cancelled
- `cod_gateway.CODPaymentRequest.status`：cod_created / cod_shipped / cod_paid / cod_failed / cod_expired / cod_cancelled


---

## 目錄

1. [路由層 Routing](#layer-1)
2. [資料模型層 Models](#layer-2)
3. [Schema 層](#layer-3)
4. [入口層 Views（驗 MAC / 回應）](#layer-4)
5. [服務層 Services（商業邏輯）](#layer-5)
6. [介面層 Interfaces（抽象 ABC）](#layer-6)
7. [轉接層 Adapters（httpx）](#layer-7)
8. [資料存取層 Repository](#layer-8)

---

<a id="layer-1"></a>

## 1. 路由層 Routing

專案根路由與兩個 app 的路由。

### 📄 `ecpay_mock/ecpay_mock/urls.py`

```python
from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView
urlpatterns = [
    path('', RedirectView.as_view(pattern_name='cod_gateway:query_and_simulate_cod', permanent=False), name='root_redirect'),
    path('atm/', RedirectView.as_view(pattern_name='gateway:query_and_simulate', permanent=False), name='root_redirect'),
    path('admin/', admin.site.urls),
    path('gateway/', include('gateway.urls')),
    path('cod_gateway/', include('cod_gateway.urls')),
]
```

### 📄 `ecpay_mock/gateway/urls.py`

```python
from django.urls import path
from gateway.views import home, ecpay_gateway_checkout, simulate_bank_paid, payment_info, payment_notify, cancel_order, order_result, download_orderPayment_json, query_and_simulate, db_query_tool, atm_info
app_name = 'gateway'
urlpatterns = [
    path('', home, name='home'),
    path('ecpay_gateway_checkout/', ecpay_gateway_checkout, name='ecpay_gateway_checkout'),
    path('simulate_bank_paid/', simulate_bank_paid, name='simulate_bank_paid'),
    path('payment_info/', payment_info, name='payment_info'),
    path('atm_info/', atm_info, name='atm_info'),
    path('payment_notify/', payment_notify, name='payment_notify'),
    path('cancel_order/', cancel_order, name='cancel_order'),
    path('order_result/', order_result, name='order_result'),
    path('download_orderPayment_json/', download_orderPayment_json, name='download_orderPayment_json'),
    path('admin-tools/query/', db_query_tool, name='db_query_tool'),
    path('admin-tools/query_and_simulate/', query_and_simulate, name='query_and_simulate'),
]
```

### 📄 `ecpay_mock/cod_gateway/urls.py`

```python
from django.urls import path
from .views import cod_checkout, select_store, review_store, confirm_store, db_query_tool, simulate_cvscod_paid, simulate_cvscod_failed, query_and_simulate_cod, mock_shipped, mock_created, simulate_cvscod_expired, cod_cancel
app_name = 'cod_gateway'
urlpatterns = [
    path('cod_checkout/', cod_checkout, name='cod_checkout'),
    path('cod_cancel/', cod_cancel, name='cod_cancel'),
    path('select_store/', select_store, name='select_store'),
    path('review_store/', review_store, name='review_store'),
    path('confirm_store/', confirm_store, name='confirm_store'),
    path('db_query_tool/', db_query_tool, name='db_query_tool'),
    path('query_and_simulate_cod/', query_and_simulate_cod, name='query_and_simulate_cod'),
    path('simulate_cvscod_paid/<str:merchant_trade_no>/', simulate_cvscod_paid, name='simulate_cvscod_paid'),
    path('simulate_cvscod_failed/<str:merchant_trade_no>/', simulate_cvscod_failed, name='simulate_cvscod_failed'),
    path('simulate_cvscod_expired/<str:merchant_trade_no>/', simulate_cvscod_expired, name='simulate_cvscod_expired'),
    path('mock_shipped/<str:merchant_trade_no>/', mock_shipped, name='mock_shipped'),
    path('mock_created/<str:merchant_trade_no>/', mock_created, name='mock_created'),
]
```

<a id="layer-2"></a>

## 2. 資料模型層 Models

共用 gateway.Order、ATM 的 PaymentRequest / PaymentNotification、COD 的 CODPaymentRequest。

### 📄 `ecpay_mock/gateway/models.py`

#### `Order`（class，原檔第 5–26 行）

```python
class Order(models.Model):
    order_number = models.CharField(max_length=50, unique=True, editable=False, null=True, blank=True)
    user_id = models.IntegerField()
    receiver_name = models.CharField(max_length=100, help_text='收件者姓名')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=[('pending', 'Pending'), ('paid', 'Paid'), ('failed', 'Failed'), ('cancelled', 'Cancelled'), ('expired', 'Expired')], default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'Order {self.order_number} - {self.status}'
```

#### `PaymentRequest`（class，原檔第 30–66 行）

```python
class PaymentRequest(models.Model):
    merchant_id = models.CharField(max_length=20)
    merchant_trade_no = models.CharField(max_length=50, unique=True)
    merchant_trade_date = models.DateTimeField()
    trade_amt = models.DecimalField(max_digits=10, decimal_places=2)
    trade_desc = models.CharField(max_length=200, default='購買商品')
    item_name = models.TextField()
    payment_type = models.CharField(max_length=20)
    choose_payment = models.CharField(max_length=20)
    trade_no = models.CharField(max_length=50, blank=True, null=True)
    bank_code = models.CharField(max_length=3)
    v_account = models.CharField(max_length=20)
    expire_date = models.DateTimeField(max_length=20, default=timezone.now)
    status = models.CharField(max_length=20, choices=[('atm_pending', 'ATM_Pending'), ('atm_created', 'ATM_Create'), ('atm_paid', 'ATM_Paid'), ('atm_failed', 'ATM_Failed'), ('atm_cancelled', 'ATM_Cancelled'), ('atm_expired', 'ATM_Expired')], default='ATM_Pending')
    check_mac_value = models.CharField(max_length=128, blank=True, null=True)
    return_url = models.URLField(blank=True, null=True)
    payment_info_url = models.URLField(blank=True, null=True)
    order_result_url = models.URLField(blank=True, null=True)

    def __str__(self):
        return f'PaymentRequest {self.merchant_trade_no}'
```

#### `PaymentNotification`（class，原檔第 70–82 行）

```python
class PaymentNotification(models.Model):
    merchant_trade_no = models.CharField(max_length=50)
    trade_no = models.CharField(max_length=50)
    trade_amt = models.DecimalField(max_digits=10, decimal_places=2)
    payment_date = models.DateTimeField()
    choose_payment = models.CharField(max_length=20)
    payment_type = models.CharField(max_length=20)
    rtn_code = models.IntegerField()
    rtn_msg = models.CharField(max_length=100)
    simulate_paid = models.BooleanField(default=False)

    def __str__(self):
        return f'Notification {self.trade_no} - Code {self.rtn_code}'
```

### 📄 `ecpay_mock/cod_gateway/models.py`

#### `CODPaymentRequest`（class，原檔第 7–76 行）
> 超商取貨付款(貨到付款, CVSCOD)請求。

```python
class CODPaymentRequest(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='cod_payment_requests', help_text='關聯到主訂單(同一家商店 E_commerce 的訂單)')
    merchant_trade_no = models.CharField(max_length=50, unique=True)
    trade_no = models.CharField(max_length=50, blank=True, default='')
    merchant_trade_date = models.DateTimeField()
    trade_amt = models.DecimalField(max_digits=10, decimal_places=2)
    item_name = models.TextField()
    receiver_name = models.CharField(max_length=100)
    receiver_address = models.CharField(max_length=255, blank=True, default='', verbose_name='收件地址')
    receiver_cell_phone = models.CharField(max_length=20, blank=True, default='')
    LOGISTICS_SUBTYPE_CHOICES = [('UNIMART', '7-ELEVEN'), ('FAMI', '全家'), ('HILIFE', '萊爾富'), ('OKMART', 'OK超商')]
    logistics_subtype = models.CharField(max_length=10, choices=LOGISTICS_SUBTYPE_CHOICES, blank=True, default='')
    store_id = models.CharField(max_length=20, blank=True, default='')
    store_name = models.CharField(max_length=100, blank=True, default='')
    store_address = models.CharField(max_length=200, blank=True, default='')
    store_lat = models.FloatField(blank=True, null=True)
    store_lng = models.FloatField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=[('cod_created', '待出貨'), ('cod_shipped', '配送中,待取貨付款'), ('cod_paid', '已取貨付款'), ('cod_failed', '取貨付款失敗'), ('cod_cancelled', '訂單已取消'), ('cod_expired', '訂單逾期未付款')], default='cod_created')
    shipped_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    check_mac_value = models.CharField(max_length=128, blank=True, null=True)
    return_url = models.URLField(blank=True, null=True)
    order_result_url = models.URLField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'CODPaymentRequest {self.merchant_trade_no} - {self.status}'
```

<a id="layer-3"></a>

## 3. Schema 層

ATM 結帳資料驗證。

### 📄 `ecpay_mock/gateway/schemas/checkout.py`

#### `ECPayCheckoutSchema`（class，原檔第 18–271 行）
> 【新增】

```python
class ECPayCheckoutSchema(Schema):
    model_config = ConfigDict(extra='forbid')
    merchant_trade_no: str = Field(min_length=1, max_length=50)
    trade_amt: Decimal = Field(gt=0)
    item_name: str = Field(default='購買商品', min_length=1, max_length=400)
    choose_payment: str = Field(default='ATM', min_length=1, max_length=20)
    merchant_id: Optional[str] = Field(default='2000132', max_length=20)
    merchant_trade_date: Optional[datetime] = None
    trade_desc: Optional[str] = Field(default='購買商品', max_length=200)
    payment_type: Optional[str] = Field(default='aio', max_length=20)
    user_id: Optional[int] = None
    receiver_name: Optional[str] = Field(default=None, max_length=100)
    ReturnURL: Optional[str] = None
    PaymentInfoURL: Optional[str] = None
    OrderResultURL: Optional[str] = None
    CheckMacValue: str = Field(min_length=1, max_length=128)

    @field_validator('choose_payment')
    @classmethod
    def validate_choose_payment(cls, value: str) -> str:
        value = value.strip().upper()
        if value != 'ATM':
            raise ValueError('目前 ECPay Mock 僅支援 ATM')
        return value

    @field_validator('merchant_trade_no')
    @classmethod
    def validate_merchant_trade_no(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError('merchant_trade_no 不可為空')
        return value

    @field_validator('trade_amt')
    @classmethod
    def validate_trade_amt(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError('trade_amt 必須大於 0')
        return value
```

<a id="layer-4"></a>

## 4. 入口層 Views（驗 MAC / 回應）

ATM：checkout、Bank callback、模擬、取消；COD：選店、確認、模擬、取消。

### 📄 `ecpay_mock/gateway/views.py`

#### `_parse_json_request`（def，原檔第 263–306 行）
> 【新增】

```python
def _parse_json_request(request) -> dict:
    if not request.body:
        raise ValueError('Request body 不可為空')
    try:
        data = json.loads(request.body.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError('Request body 必須是合法 JSON') from exc
    if not isinstance(data, dict):
        raise ValueError('JSON 根節點必須是 object')
    return data
```

#### `_verify_check_mac_value`（def，原檔第 313–437 行）
> 【新增】

```python
def _verify_check_mac_value(data: dict) -> str:
    if not isinstance(data, dict):
        raise ValueError('CheckMacValue 驗證資料格式錯誤')
    incoming_check_mac = data.get('CheckMacValue')
    if not incoming_check_mac:
        raise ValueError('缺少 CheckMacValue')
    hash_key = getattr(settings, 'ECPAY_HASH_KEY', '')
    hash_iv = getattr(settings, 'ECPAY_HASH_IV', '')
    if not hash_key or not hash_iv:
        raise RuntimeError('ECPAY_HASH_KEY / ECPAY_HASH_IV 未設定')
    verify_data = dict(data)
    verify_data.pop('CheckMacValue', None)
    try:
        expected_check_mac = generate_check_mac_value(verify_data, hash_key, hash_iv)
    except Exception as exc:
        logger.exception('CheckMacValue 計算失敗')
        raise RuntimeError('CheckMacValue 驗證處理失敗') from exc
    if not hmac.compare_digest(str(expected_check_mac).upper(), str(incoming_check_mac).upper()):
        raise ValueError('CheckMacValue 驗證失敗')
    return str(incoming_check_mac)
```

#### `get_ecpay_service`（def，原檔第 444–477 行）
> 【修改】

```python
def get_ecpay_service():
    try:
        return ECPayService()
    except Exception as exc:
        logger.exception('取得 ECPayService 失敗')
        raise RuntimeError('ECPayService 初始化失敗') from exc
```

#### `ecpay_gateway_checkout`（def，原檔第 1406–1746 行）
> 【新增】

```python
@csrf_exempt
def ecpay_gateway_checkout(request):
    view_name = 'ecpay_gateway_checkout'
    if request.method != 'POST':
        return JsonResponse({'status': False, 'error': 'MethodNotAllowed', 'message': '只接受 POST Request', 'view': view_name}, status=405)
    try:
        if request.POST:
            data = request.POST.dict()
        else:
            data = _parse_json_request(request)
        incoming_check_mac = _verify_check_mac_value(data)
        data['CheckMacValue'] = incoming_check_mac
        if not data.get('merchant_trade_no'):
            raise ValueError('建立 ATM 付款缺少 merchant_trade_no')
        if data.get('trade_amt') in (None, ''):
            raise ValueError('建立 ATM 付款缺少 trade_amt')
        service = get_ecpay_service()
        result = service.create_atm_payment(request_data=data)
        if not isinstance(result, dict):
            raise RuntimeError('ECPayService 回傳格式錯誤')
        if not result.get('status', False):
            raise RuntimeError(result.get('message', 'ATM 建立失敗'))
        payment = result.get('payment')
        if not isinstance(payment, dict):
            raise RuntimeError('ATM 建立成功但缺少 payment 資料')
        content = {'content_js_dict': payment, 'content_js_json': json.dumps(payment, ensure_ascii=False, default=str), 'HF_SPACE_E_COMMERCE_URL': settings.HF_SPACE_E_COMMERCE_URL}
        atm_info_url = result.get('atm_info_url')
        if not atm_info_url:
            raise RuntimeError('ATM 建立成功，但缺少 atm_info_url')
        return redirect(atm_info_url)
    except ValueError as exc:
        logger.warning('%s | ATM checkout validation failed: %s', view_name, str(exc))
        return JsonResponse({'status': False, 'error': 'BadRequest', 'message': str(exc), 'view': view_name}, status=400)
    except RuntimeError as exc:
        logger.exception('%s | ATM checkout processing failed', view_name)
        return JsonResponse({'status': False, 'error': 'CheckoutError', 'message': str(exc), 'view': view_name}, status=500)
    except Exception:
        logger.exception('%s | Unexpected ATM checkout error', view_name)
        return JsonResponse({'status': False, 'error': 'ServerError', 'message': 'ATM 建立發生未預期錯誤', 'view': view_name}, status=500)
```

#### `payment_notify`（def，原檔第 657–904 行）
> 【修改】

```python
@csrf_exempt
def payment_notify(request):
    view_name = 'payment_notify'
    if request.method != 'POST':
        return JsonResponse({'status': False, 'error': 'MethodNotAllowed', 'message': '只接受 POST Request', 'view': view_name}, status=405)
    try:
        if request.POST:
            data = request.POST.dict()
        else:
            data = _parse_json_request(request)
        incoming_check_mac = _verify_check_mac_value(data)
        data['CheckMacValue'] = incoming_check_mac
        if not data.get('merchant_trade_no'):
            raise ValueError('付款通知缺少 merchant_trade_no')
        if data.get('trade_amt') in (None, ''):
            raise ValueError('付款通知缺少 trade_amt')
        service = get_ecpay_service()
        result = service.process_payment_notification(request_data=data)
        return JsonResponse(result, status=200)
    except ValueError as exc:
        logger.warning('%s | Callback validation failed: %s', view_name, str(exc))
        return JsonResponse({'status': False, 'error': 'BadRequest', 'message': str(exc), 'view': view_name}, status=400)
    except RuntimeError as exc:
        logger.exception('%s | Callback processing failed', view_name)
        return JsonResponse({'status': False, 'error': 'CallbackError', 'message': str(exc), 'view': view_name}, status=500)
    except Exception:
        logger.exception('%s | Unexpected callback error', view_name)
        return JsonResponse({'status': False, 'error': 'ServerError', 'message': '付款通知處理發生未預期錯誤', 'view': view_name}, status=500)
```

#### `simulate_bank_paid`（def，原檔第 2159–2284 行）

```python
@csrf_exempt
@transaction.atomic
def simulate_bank_paid(request):
    if request.method != 'POST':
        return HttpResponse('method error')
    try:
        payment_payload = request.POST.dict() if request.POST else request.body
        print('1')
        if isinstance(payment_payload, (bytes, bytearray)):
            payment_payload = json.loads(payment_payload.decode('utf-8'))
            print('payment_payload: ', payment_payload)
    except json.JSONDecodeError:
        return HttpResponseBadRequest('JSON 格式錯誤')
    print('2')
    received_mac = payment_payload.pop('check_mac_value', '')
    expected_mac = generate_check_mac_value(payment_payload, settings.ECPAY_HASH_KEY, settings.ECPAY_HASH_IV)
    print('received_mac =', received_mac)
    print('expected_mac =', expected_mac)
    print('payment_payload =', payment_payload)
    if received_mac != expected_mac:
        return HttpResponse('CheckMacValue Error', status=400)
    merchant_trade_no = payment_payload.get('merchant_trade_no')
    payment_request = PaymentRequest.objects.get(merchant_trade_no=merchant_trade_no)
    print('payment_request: ', payment_request)
    payment_request.status = 'atm_paid'
    payment_request.save()
    order, created = Order.objects.get_or_create(order_number=merchant_trade_no, defaults={'user_id': payment_payload['user_id'], 'receiver_name': '王大明', 'amount': payment_payload['trade_amt'], 'status': 'paid'})
    print('3')
    if payment_request.status == 'atm_paid':
        payment_notification = PaymentNotification.objects.create(merchant_trade_no=payment_request.merchant_trade_no, trade_no=payment_request.trade_no, trade_amt=payment_request.trade_amt, payment_date=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), choose_payment=payment_request.choose_payment, payment_type=payment_request.payment_type, rtn_code=1, rtn_msg='交易成功', simulate_paid=True)
    payment_payload = {'merchant_id': payment_payload.get('merchant_id', 'shop1234'), 'merchant_trade_no': merchant_trade_no, 'merchant_trade_date': payment_payload['merchant_trade_date'], 'user_id': payment_payload['user_id'], 'trade_amt': payment_payload['trade_amt'], 'trade_desc': payment_payload['trade_desc'], 'item_name': payment_payload['item_name'], 'choose_payment': payment_payload['choose_payment'], 'payment_type': payment_payload['payment_type'], 'trade_no': payment_payload['trade_no'], 'return_url': payment_payload['return_url'], 'payment_info_url': payment_payload['payment_info_url'], 'order_result_url': payment_payload['order_result_url'], 'bank_code': payment_payload['bank_code'], 'v_account': payment_payload['v_account'], 'expire_date': payment_payload['expire_date']}
    order_pay_at = f'{str(payment_notification.payment_date)}'
    print('order_pay_at:', order_pay_at)
    payment_payload['order_pay_at'] = order_pay_at
    payment_payload['check_mac_value'] = generate_check_mac_value(payment_payload, settings.ECPAY_HASH_KEY, settings.ECPAY_HASH_IV)
    content = {'payment_payload': payment_payload}
    print('payment_payload: ', payment_payload)
    content = {'payment_payload_dict': payment_payload, 'payment_payload_json': json.dumps(payment_payload, ensure_ascii=False, default=str), 'HF_SPACE_E_COMMERCE_URL': HF_SPACE_E_COMMERCE_URL}
    return render(request, 'redirect_html.html', content)
```

#### `atm_info`（def，原檔第 1895–2101 行）
> 【修改】

```python
@csrf_exempt
def atm_info(request):
    if request.method != 'GET':
        return JsonResponse({'status': False, 'message': '只允許 GET'}, status=405)
    merchant_trade_no = request.GET.get('merchant_trade_no')
    if not merchant_trade_no:
        return JsonResponse({'status': False, 'message': '缺少 merchant_trade_no'}, status=400)
    merchant_trade_no = str(merchant_trade_no).strip()
    if not merchant_trade_no:
        return JsonResponse({'status': False, 'message': 'merchant_trade_no 不可為空'}, status=400)
    try:
        service = get_ecpay_service()
        payment = service.get_atm_payment_info(merchant_trade_no=merchant_trade_no)
        content = {'content_js_dict': payment, 'content_js_json': json.dumps(payment, ensure_ascii=False, default=str), 'HF_SPACE_E_COMMERCE_URL': settings.HF_SPACE_E_COMMERCE_URL}
        return render(request, 'atm_info.html', content)
    except ValueError as exc:
        logger.warning('ATM info 查詢失敗：%s', exc)
        return JsonResponse({'status': False, 'message': str(exc)}, status=404)
    except Exception as exc:
        logger.exception('ATM info 顯示發生未預期錯誤')
        return JsonResponse({'status': False, 'message': f'ATM 資訊顯示失敗：{exc}'}, status=500)
```

#### `order_result`（def，原檔第 2488–2534 行）

```python
def order_result(request):
    try:
        context = request.POST.dict() if request.POST else request.body
        print('context:', context)
        if isinstance(context, (bytes, bytearray)):
            context = json.loads(context.decode('utf-8'))
            print('context: ', context)
    except json.JSONDecodeError:
        return HttpResponseBadRequest('JSON 格式錯誤')
    print('2')
    received_mac = context.copy()
    received_mac = received_mac.pop('check_mac_value', '')
    context1 = context.pop('check_mac_value', '')
    expected_mac = generate_check_mac_value(context, settings.ECPAY_HASH_KEY, settings.ECPAY_HASH_IV)
    print('received_mac =', received_mac)
    print('expected_mac =', expected_mac)
    print('context =', context)
    if received_mac != expected_mac:
        return HttpResponse('CheckMacValue Error', status=400)
    context['check_mac_value'] = generate_check_mac_value(context, settings.ECPAY_HASH_KEY, settings.ECPAY_HASH_IV)
    content = {'content_js': context}
    html = f'''\n    <form id="f" action=f"{settings.HF_SPACE_E_COMMERCE_URL}/commerce_shop/payment_ok/" method="post">\n        <input type="hidden" name="content_js" value="{content['content_js']}">\n    </form>\n    <script>\n        document.getElementById('f').submit();\n    </script>\n    '''
    return HttpResponse(html)
```

#### `cancel_order`（def，原檔第 2759–2807 行）

```python
@csrf_exempt
def cancel_order(request):
    if request.method != 'POST':
        return JsonResponse({'status': False, 'message': '只接受 POST Request'}, status=405)
    try:
        data = _parse_json_request(request)
        _verify_check_mac_value(data)
        merchant_trade_no = data.get('merchant_trade_no')
        if not merchant_trade_no:
            return JsonResponse({'status': False, 'message': '缺少 merchant_trade_no'}, status=400)
        service = get_ecpay_service()
        result = service.cancel_order(merchant_trade_no=str(merchant_trade_no))
    except LookupError as ex:
        return JsonResponse({'status': False, 'message': str(ex)}, status=200)
    except ValueError as ex:
        return JsonResponse({'status': False, 'message': str(ex)}, status=200)
    except RuntimeError as ex:
        logger.exception('ecpay_mock 取消訂單：下游失敗')
        return JsonResponse({'status': False, 'message': str(ex)}, status=200)
    except Exception as ex:
        logger.exception('ecpay_mock 取消訂單發生未預期錯誤')
        return JsonResponse({'status': False, 'message': '取消訂單失敗', 'error': str(ex)}, status=500)
    return JsonResponse(result, status=200)
```

### 📄 `ecpay_mock/cod_gateway/views.py`

#### `cod_checkout`（def，原檔第 841–892 行）

```python
@csrf_exempt
def cod_checkout(request):
    if request.method != 'POST':
        return HttpResponse('method error', status=405)
    try:
        payment_data = request.POST.dict() if request.POST else request.body
        if isinstance(payment_data, (bytes, bytearray)):
            payment_data = json.loads(payment_data.decode('utf-8'))
    except json.JSONDecodeError as e:
        return _log_and_build_error_response('cod_checkout.parse_request', e, status=400)
    except Exception as e:
        return _log_and_build_error_response('cod_checkout.parse_request_unexpected', e, status=400)
    try:
        mac_a = payment_data.pop('CheckMacValue', '')
        mac_b = payment_data.pop('check_mac_value', '')
        received_mac = mac_a or mac_b
        expected_mac = generate_check_mac_value(payment_data, settings.ECPAY_HASH_KEY, settings.ECPAY_HASH_IV)
    except Exception as e:
        return _log_and_build_error_response('cod_checkout.generate_mac', e, status=400)
    if not received_mac or not hmac.compare_digest(str(received_mac).upper(), str(expected_mac).upper()):
        logger.warning('[cod_checkout] CheckMacValue 不符')
        return HttpResponse('CheckMacValue Error', status=400)
    try:
        checkout_data = CODService().prepare_checkout(payment_data)
        checkout_data['check_mac_value'] = str(received_mac)
    except ValueError as e:
        return _log_and_build_error_response('cod_checkout.validate', e, status=400)
    except Exception as e:
        return _log_and_build_error_response('cod_checkout.unexpected', e, status=500)
    try:
        request.session['cod_checkout_data'] = checkout_data
        request.session['cod_merchant_trade_no'] = checkout_data['merchant_trade_no']
    except Exception as e:
        return _log_and_build_error_response('cod_checkout.session_write', e, status=500)
    return redirect('cod_gateway:select_store')
```

#### `select_store`（def，原檔第 1015–1035 行）
> 模擬綠界電子地圖:顯示門市清單 + 小地圖,讓使用者選擇取貨門市。

```python
def select_store(request):
    try:
        merchant_trade_no = request.session.get('cod_merchant_trade_no')
        if not merchant_trade_no:
            raise ValueError('找不到對應的訂單編號(session 已遺失),請重新從商城結帳')
        context = {'stores_json': json.dumps(MOCK_STORES, ensure_ascii=False), 'merchant_trade_no': merchant_trade_no}
        return render(request, 'select_store.html', context)
    except ValueError as e:
        return _log_and_build_error_response('select_store.session_missing', e, status=400)
    except Exception as e:
        return _log_and_build_error_response('select_store.unexpected', e, status=500)
```

#### `review_store`（def，原檔第 1234–1284 行）
> 【新增】選店後的「確認頁」:

```python
def review_store(request):
    if request.method != 'POST':
        return HttpResponse('method error', status=405)
    try:
        merchant_trade_no = request.session.get('cod_merchant_trade_no')
        if not merchant_trade_no:
            raise ValueError('session 已遺失,找不到對應訂單,請重新從商城結帳')
        store_id = request.POST.get('store_id')
        store = next((s for s in MOCK_STORES if s['store_id'] == store_id), None)
        if not store:
            raise ValueError(f"門市代號 '{store_id}' 不存在,請重新選擇")
    except ValueError as e:
        return _log_and_build_error_response('review_store.validate_input', e, status=400)
    except Exception as e:
        return _log_and_build_error_response('review_store.validate_input_unexpected', e, status=500)
    checkout_data = request.session.get('cod_checkout_data')
    if not checkout_data:
        return _log_and_build_error_response('review_store.checkout_data_missing', ValueError('結帳資料已遺失，請重新從商城結帳'), status=400)
    cod_payment = SimpleNamespace(**checkout_data)
    context = {'store': store, 'cod_payment': cod_payment, 'merchant_trade_no': merchant_trade_no, 'HF_SPACE_E_COMMERCE_URL': settings.HF_SPACE_E_COMMERCE_URL}
    return render(request, 'review_store.html', context)
```

#### `confirm_store`（def，原檔第 1042–1103 行）

```python
@csrf_exempt
def confirm_store(request):
    if request.method != 'POST':
        return HttpResponse('method error', status=405)
    try:
        merchant_trade_no = request.session.get('cod_merchant_trade_no')
        if not merchant_trade_no:
            raise ValueError('session 已遺失,找不到對應訂單,請重新從商城結帳')
        store_id = request.POST.get('store_id')
        store = next((s for s in MOCK_STORES if s['store_id'] == store_id), None)
        if not store:
            raise ValueError(f"門市代號 '{store_id}' 不存在,請重新選擇")
    except ValueError as e:
        return _log_and_build_error_response('confirm_store.validate_input', e, status=400)
    except Exception as e:
        return _log_and_build_error_response('confirm_store.validate_input_unexpected', e, status=500)
    existing = CODPaymentRequest.objects.filter(merchant_trade_no=merchant_trade_no).first()
    if existing and existing.store_id:
        logger.info(f'[confirm_store] 訂單 {merchant_trade_no} 已確認過門市,直接顯示既有結果')
        request.session.pop('cod_merchant_trade_no', None)
        request.session.pop('cod_checkout_data', None)
        return render(request, 'cod_info.html', {'cod': existing, 'HF_SPACE_E_COMMERCE_URL': settings.HF_SPACE_E_COMMERCE_URL})
    try:
        cod_payment = CODService().confirm_store(checkout_data=request.session.get('cod_checkout_data'), store=store)
    except ValueError as e:
        return _log_and_build_error_response('confirm_store.validate', e, status=400)
    except RuntimeError as e:
        logger.exception(f'[confirm_store.notify_shop_failed] 訂單 {merchant_trade_no}')
        return render(request, 'cod_error.html', {'error_message': f'通知商城失敗,您選擇的門市尚未確認成功,請返回商店訂單頁面重新操作。（{e}）', 'merchant_trade_no': merchant_trade_no, 'HF_SPACE_E_COMMERCE_URL': settings.HF_SPACE_E_COMMERCE_URL}, status=502)
    except Exception:
        logger.exception(f'[confirm_store.db_write_unexpected] 訂單 {merchant_trade_no}')
        return render(request, 'cod_error.html', {'error_message': '系統發生錯誤,門市確認失敗,請返回商店訂單頁面重新操作。', 'merchant_trade_no': merchant_trade_no, 'HF_SPACE_E_COMMERCE_URL': settings.HF_SPACE_E_COMMERCE_URL}, status=500)
    request.session.pop('cod_merchant_trade_no', None)
    request.session.pop('cod_checkout_data', None)
    return render(request, 'cod_info.html', {'cod': cod_payment, 'HF_SPACE_E_COMMERCE_URL': settings.HF_SPACE_E_COMMERCE_URL})
```

#### `query_and_simulate_cod`（def，原檔第 586–633 行）
> 合併頁面（COD 版）:左側是 SQL 查詢工具（邏輯與 Bank_site 版本完全相同，原樣搬過來），

```python
@csrf_exempt
@user_passes_test(is_admin, login_url='/admin/login/')
def query_and_simulate_cod(request):
    tables = []
    columns = []
    rows = []
    error = None
    table_choice = request.GET.get('table', '')
    column_choice = request.GET.get('column', '')
    with connection.cursor() as cursor:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name NOT LIKE 'django_%' AND name NOT LIKE 'auth_%';")
        tables = [r[0] for r in cursor.fetchall()]
        if table_choice and table_choice in tables:
            cursor.execute(f'PRAGMA table_info({table_choice});')
            columns = [r[1] for r in cursor.fetchall()]
            if column_choice and column_choice in columns:
                try:
                    query = f'SELECT {column_choice} FROM {table_choice} WHERE {column_choice} IS NOT NULL;'
                    cursor.execute(query)
                    rows = [{column_choice: r[0]} for r in cursor.fetchall()]
                except Exception as e:
                    error = str(e)
    context = {'tables': tables, 'columns': columns, 'rows': rows, 'error': error, 'table_choice': table_choice, 'column_choice': column_choice}
    return render(request, 'admin_tools/query_simulate_cod.html', context)
```

#### `_run_simulation`（def，原檔第 638–657 行）

```python
def _run_simulation(request, merchant_trade_no, action, label):
    try:
        CODService().simulate(merchant_trade_no, action)
    except LookupError:
        return JsonResponse({'status': 'failed', 'message': '找不到該筆訂單編號'}, status=404)
    except ValueError as ex:
        return JsonResponse({'status': 'failed', 'message': str(ex)}, status=400)
    except Exception as ex:
        logger.exception(f'[simulate:{action}] 訂單 {merchant_trade_no} 失敗')
        return JsonResponse({'status': 'failed', 'message': f'{label}失敗，ecpay 未更新：{ex}'}, status=500)
    msg = f'訂單 {merchant_trade_no}「{label}」成功，已同步通知商店！'
    messages.success(request, msg)
    return JsonResponse({'status': 'success', 'message': msg}, status=200)
```

#### `simulate_cvscod_paid`（def，原檔第 662–663 行）

```python
@csrf_exempt
@user_passes_test(is_admin, login_url='/admin/login/')
def simulate_cvscod_paid(request, merchant_trade_no):
    return _run_simulation(request, merchant_trade_no, 'paid', '已取貨付款')
```

#### `simulate_cvscod_failed`（def，原檔第 752–753 行）

```python
@csrf_exempt
@user_passes_test(is_admin, login_url='/admin/login/')
def simulate_cvscod_failed(request, merchant_trade_no):
    return _run_simulation(request, merchant_trade_no, 'failed', '取貨失敗未付款')
```

#### `simulate_cvscod_expired`（def，原檔第 758–759 行）

```python
@csrf_exempt
@user_passes_test(is_admin, login_url='/admin/login/')
def simulate_cvscod_expired(request, merchant_trade_no):
    return _run_simulation(request, merchant_trade_no, 'expired', '逾期未付款')
```

#### `mock_shipped`（def，原檔第 1419–1420 行）

```python
@csrf_exempt
@user_passes_test(is_admin, login_url='/admin/login/')
def mock_shipped(request, merchant_trade_no):
    return _run_simulation(request, merchant_trade_no, 'shipped', '貨品已送達超商')
```

#### `mock_created`（def，原檔第 1532–1533 行）

```python
@csrf_exempt
@user_passes_test(is_admin, login_url='/admin/login/')
def mock_created(request, merchant_trade_no):
    return _run_simulation(request, merchant_trade_no, 'created', '貨品未送達超商（待出貨）')
```

#### `cod_cancel`（def，原檔第 1769–1818 行）

```python
@csrf_exempt
def cod_cancel(request):
    if request.method != 'POST':
        return JsonResponse({'status': False, 'message': '只接受 POST Request'}, status=405)
    try:
        data = json.loads(request.body.decode('utf-8')) if request.body else {}
        mac_a = data.pop('CheckMacValue', '')
        mac_b = data.pop('check_mac_value', '')
        received_mac = mac_a or mac_b
        expected_mac = generate_check_mac_value(data, settings.ECPAY_HASH_KEY, settings.ECPAY_HASH_IV)
        if not received_mac or not hmac.compare_digest(str(received_mac).upper(), str(expected_mac).upper()):
            logger.warning('[cod_cancel] CheckMacValue 不符')
            return JsonResponse({'status': False, 'message': 'CheckMacValue 不符'}, status=400)
        merchant_trade_no = data.get('merchant_trade_no')
        if not merchant_trade_no:
            return JsonResponse({'status': False, 'message': '缺少 merchant_trade_no'}, status=400)
        result = CODService().cancel(str(merchant_trade_no))
    except ValueError as ex:
        return JsonResponse({'status': False, 'message': str(ex)}, status=200)
    except Exception as ex:
        logger.exception('ecpay_mock 取消 COD 訂單發生未預期錯誤')
        return JsonResponse({'status': False, 'message': '取消訂單失敗', 'error': str(ex)}, status=500)
    return JsonResponse(result, status=200)
```

<a id="layer-5"></a>

## 5. 服務層 Services（商業邏輯）

ATM 建立 / 通知處理 / 取消；COD 結帳、確認門市、模擬、取消。

### 📄 `ecpay_mock/gateway/services/ecpay_service.py`

#### `ECPayService.__init__`（原檔第 102–156 行）
> 【修改】

```python
def __init__(self, ecpay_gateway=None, store_payment_gateway=None):
    self.ecpay_gateway = ecpay_gateway or ECPayMockAdapter()
    self.store_payment_gateway = store_payment_gateway or StorePaymentAdapter()
```

#### `ECPayService.get_atm_payment_info`（原檔第 163–291 行）
> 【新增】

```python
def get_atm_payment_info(self, *, merchant_trade_no: str) -> Dict[str, Any]:
    if not merchant_trade_no:
        raise ValueError('查詢 ATM 資訊缺少 merchant_trade_no')
    merchant_trade_no = str(merchant_trade_no).strip()
    if not merchant_trade_no:
        raise ValueError('merchant_trade_no 不可為空')
    payment_request = PaymentRequest.objects.filter(merchant_trade_no=merchant_trade_no).first()
    if payment_request is None:
        raise ValueError('找不到對應的 PaymentRequest')
    if not payment_request.bank_code:
        raise ValueError('PaymentRequest 缺少 bank_code')
    if not payment_request.v_account:
        raise ValueError('PaymentRequest 缺少 v_account')
    if not payment_request.expire_date:
        raise ValueError('PaymentRequest 缺少 expire_date')
    return {'merchant_id': str(payment_request.merchant_id), 'merchant_trade_no': merchant_trade_no, 'merchant_trade_date': payment_request.merchant_trade_date, 'trade_amt': str(payment_request.trade_amt), 'trade_desc': payment_request.trade_desc, 'item_name': payment_request.item_name, 'choose_payment': payment_request.choose_payment, 'payment_type': payment_request.payment_type, 'trade_no': str(payment_request.trade_no) if payment_request.trade_no else None, 'bank_code': str(payment_request.bank_code), 'v_account': str(payment_request.v_account), 'expire_date': payment_request.expire_date, 'status': payment_request.status}
```

#### `ECPayService.create_atm_payment`（原檔第 1387–2163 行）
> 【修改】

```python
def create_atm_payment(self, *, request_data: Dict[str, Any]) -> Dict[str, Any]:
    try:
        if not isinstance(request_data, dict):
            raise ValueError('request_data 必須是 dict')
        merchant_trade_no = request_data.get('merchant_trade_no')
        trade_amt = request_data.get('trade_amt')
        item_name = request_data.get('item_name') or '購買商品'
        choose_payment = request_data.get('choose_payment') or 'ATM'
        if not merchant_trade_no:
            raise ValueError('缺少 merchant_trade_no')
        if trade_amt in (None, ''):
            raise ValueError('缺少 trade_amt')
        if choose_payment != 'ATM':
            raise ValueError('目前 ECPay Mock 僅支援 ATM')
        merchant_trade_no = str(merchant_trade_no)
        try:
            amount = int(Decimal(str(trade_amt)))
        except (TypeError, ValueError) as exc:
            raise ValueError('trade_amt 格式錯誤') from exc
        if amount <= 0:
            raise ValueError('trade_amt 必須大於 0')
        try:
            existing_payment = PaymentRequest.objects.filter(merchant_trade_no=merchant_trade_no).first()
        except Exception as exc:
            logger.exception('查詢既有 PaymentRequest 失敗')
            raise RuntimeError('PaymentRequest 查詢失敗') from exc
        if existing_payment is not None:
            logger.info('PaymentRequest 已存在，準備重新確認 Store Payment：merchant_trade_no=%s', merchant_trade_no)
            existing_response = self._build_atm_response(existing_payment)
            existing_payment_data = existing_response['payment']
            store_callback_payload = {'merchant_trade_no': existing_payment.merchant_trade_no, 'trade_no': str(existing_payment.trade_no), 'provider_transaction_id': str(existing_payment.trade_no), 'trade_amt': str(existing_payment.trade_amt), 'status': 'atm_created', 'payment_status': 'atm_created', 'rtn_code': 0, 'rtn_msg': 'ATM 付款資訊已存在', 'choose_payment': existing_payment.choose_payment, 'payment_type': existing_payment.payment_type, 'payment_date': timezone.now().isoformat(), 'bank_code': str(existing_payment.bank_code), 'v_account': str(existing_payment.v_account), 'expire_date': existing_payment.expire_date.isoformat(), 'atm_info_url': existing_response['atm_info_url']}
            store_callback_result = self._notify_store_payment_result(store_callback_payload)
            self._ensure_gateway_order(request_data, merchant_trade_no, amount)
            existing_response['store_callback'] = store_callback_result
            return existing_response
        gateway_payload = {'merchant_trade_no': merchant_trade_no, 'trade_amt': str(amount), 'item_name': str(item_name), 'choose_payment': 'ATM'}
        try:
            atm_result = self.ecpay_gateway.create_atm_payment(gateway_payload)
        except ValueError:
            raise
        except RuntimeError:
            raise
        except Exception as exc:
            logger.exception('ECPay Gateway / Bank Mock 呼叫失敗')
            raise RuntimeError('ATM 付款建立失敗') from exc
        if not isinstance(atm_result, dict):
            raise RuntimeError('ECPay Gateway 回傳格式錯誤')
        if not atm_result.get('success'):
            raise RuntimeError('Bank Mock ATM 建立失敗')
        response_merchant_trade_no = atm_result.get('merchant_trade_no')
        if not response_merchant_trade_no:
            raise RuntimeError('Gateway 回應缺少 merchant_trade_no')
        if str(response_merchant_trade_no) != merchant_trade_no:
            raise RuntimeError('Gateway merchant_trade_no 不一致')
        bank_code = atm_result.get('bank_code')
        v_account = atm_result.get('v_account')
        expire_date = atm_result.get('expire_date')
        payment_status = atm_result.get('payment_status') or 'pending'
        if not bank_code:
            raise RuntimeError('缺少 bank_code')
        if not v_account:
            raise RuntimeError('缺少 v_account')
        if not expire_date:
            raise RuntimeError('缺少 expire_date')
        expire_datetime = self._normalize_expire_date(expire_date)
        if expire_datetime <= timezone.now():
            raise ValueError('ATM 付款期限必須晚於目前時間')
        trade_no = 'EC' + uuid.uuid4().hex[:18].upper()
        incoming_check_mac = request_data.get('CheckMacValue')
        payment_data = {'merchant_id': request_data.get('merchant_id', '2000132'), 'merchant_trade_no': merchant_trade_no, 'merchant_trade_date': self._get_trade_date(request_data), 'trade_amt': amount, 'trade_desc': request_data.get('trade_desc', '購買商品'), 'item_name': str(item_name), 'payment_type': request_data.get('payment_type', 'aio'), 'choose_payment': 'ATM', 'trade_no': trade_no, 'bank_code': str(bank_code), 'v_account': str(v_account), 'expire_date': expire_datetime, 'status': 'atm_created', 'check_mac_value': incoming_check_mac, 'return_url': request_data.get('ReturnURL'), 'payment_info_url': request_data.get('PaymentInfoURL'), 'order_result_url': request_data.get('OrderResultURL')}
        try:
            payment_request = PaymentRequest(**payment_data)
        except Exception as exc:
            logger.exception('PaymentRequest 建立失敗')
            raise RuntimeError('ECPay ATM PaymentRequest 建立失敗') from exc
        atm_response = self._build_atm_response(payment_request)
        atm_payment = atm_response.get('payment', {})
        store_callback_payload = {'merchant_trade_no': payment_request.merchant_trade_no, 'trade_no': str(payment_request.trade_no), 'provider_transaction_id': str(payment_request.trade_no), 'trade_amt': str(payment_request.trade_amt), 'status': 'atm_created', 'payment_status': 'atm_created', 'rtn_code': 0, 'rtn_msg': 'ATM 付款資訊建立成功', 'choose_payment': payment_request.choose_payment, 'payment_type': payment_request.payment_type, 'payment_date': timezone.now().isoformat(), 'bank_code': str(payment_request.bank_code), 'v_account': str(payment_request.v_account), 'expire_date': payment_request.expire_date.isoformat(), 'atm_info_url': atm_response['atm_info_url']}
        store_callback_result = self._notify_store_payment_result(store_callback_payload)
        payment_request.save()
        self._ensure_gateway_order(request_data, merchant_trade_no, amount)
        logger.info('ECPay ATM 建立完成並已通知 Store：merchant_trade_no=%s, trade_no=%s, bank_code=%s', merchant_trade_no, trade_no, bank_code)
        atm_response['store_callback'] = store_callback_result
        return atm_response
    except ValueError:
        raise
    except RuntimeError:
        raise
    except Exception as exc:
        logger.exception('ECPayService.create_atm_payment 發生未預期錯誤')
        raise RuntimeError('ATM 付款建立失敗') from exc
```

#### `ECPayService.process_payment_notification`（原檔第 527–1262 行）
> 【新增】

```python
def process_payment_notification(self, *, request_data: Dict[str, Any]) -> Dict[str, Any]:
    try:
        if not isinstance(request_data, dict):
            raise ValueError('payment notification 必須是 dict')
        merchant_trade_no = request_data.get('merchant_trade_no')
        if not merchant_trade_no:
            raise ValueError('付款通知缺少 merchant_trade_no')
        merchant_trade_no = str(merchant_trade_no)
        payment_request = PaymentRequest.objects.filter(merchant_trade_no=merchant_trade_no).first()
        if payment_request is None:
            raise ValueError('找不到對應的 PaymentRequest')
        incoming_trade_amt = request_data.get('trade_amt')
        if incoming_trade_amt in (None, ''):
            raise ValueError('付款通知缺少 trade_amt')
        try:
            incoming_amount = Decimal(str(incoming_trade_amt))
        except (TypeError, ValueError) as exc:
            raise ValueError('付款通知 trade_amt 格式錯誤') from exc
        stored_amount = Decimal(str(payment_request.trade_amt))
        if incoming_amount != stored_amount:
            raise ValueError('付款通知 trade_amt 與 PaymentRequest 不一致')
        payment_status = request_data.get('payment_status')
        if payment_status is None:
            payment_status = request_data.get('PaymentStatus')
        if payment_status is None:
            payment_status = request_data.get('status')
        normalized_status = str(payment_status or '').strip().lower()
        rtn_code = request_data.get('rtn_code')
        if rtn_code is None:
            rtn_code = request_data.get('RtnCode')
        success_values = {'paid', 'success', 'succeeded', '1'}
        failed_values = {'failed', 'failure', 'error', '0', 'atm_failed'}
        expired_values = {'expired', 'atm_expired'}
        is_expired = False
        if normalized_status in success_values:
            is_paid = True
        elif normalized_status in failed_values:
            is_paid = False
        elif normalized_status in expired_values:
            is_paid = False
            is_expired = True
        elif str(rtn_code) == '1':
            is_paid = True
        elif str(rtn_code) == '0':
            is_paid = False
        else:
            raise ValueError('無法判斷付款通知結果')
        if is_paid:
            payment_request_status = 'atm_paid'
            normalized_payment_status = 'paid'
            normalized_rtn_code = 1
            default_message = 'ATM 付款成功'
        elif is_expired:
            payment_request_status = 'atm_expired'
            normalized_payment_status = 'expired'
            normalized_rtn_code = 0
            default_message = 'ATM 逾期未付款'
        else:
            payment_request_status = 'atm_failed'
            normalized_payment_status = 'failed'
            normalized_rtn_code = 0
            default_message = 'ATM 付款失敗'
        payment_date = self._get_payment_date(request_data)
        trade_no = request_data.get('trade_no') or payment_request.trade_no
        if not trade_no:
            raise ValueError('付款通知缺少 trade_no')
        payment_request_data = {'status': payment_request_status}
        if request_data.get('bank_code'):
            payment_request_data['bank_code'] = str(request_data['bank_code'])
        if request_data.get('v_account'):
            payment_request_data['v_account'] = str(request_data['v_account'])
        if request_data.get('expire_date'):
            payment_request_data['expire_date'] = self._normalize_expire_date(request_data['expire_date'])
        notification_data = {'merchant_trade_no': merchant_trade_no, 'trade_no': str(trade_no), 'trade_amt': incoming_amount, 'payment_date': payment_date, 'choose_payment': request_data.get('choose_payment') or payment_request.choose_payment or 'ATM', 'payment_type': request_data.get('payment_type') or payment_request.payment_type or 'aio', 'rtn_code': normalized_rtn_code, 'rtn_msg': request_data.get('rtn_msg') or request_data.get('RtnMsg') or default_message, 'simulate_paid': is_paid}
        expire_value = payment_request_data.get('expire_date') or payment_request.expire_date
        store_payload = {'merchant_trade_no': merchant_trade_no, 'trade_no': str(trade_no), 'trade_amt': str(incoming_amount), 'status': normalized_payment_status, 'rtn_code': normalized_rtn_code, 'rtn_msg': notification_data['rtn_msg'], 'choose_payment': notification_data['choose_payment'], 'payment_type': notification_data['payment_type'], 'payment_date': payment_date.isoformat(), 'bank_code': payment_request_data.get('bank_code') or payment_request.bank_code or None, 'v_account': payment_request_data.get('v_account') or payment_request.v_account or None, 'expire_date': expire_value.isoformat() if hasattr(expire_value, 'isoformat') else str(expire_value) if expire_value else None}
        store_payload['simulate'] = str(request_data.get('simulate', ''))
        try:
            callback_result = self.store_payment_gateway.notify_payment_result(store_payload)
        except ValueError:
            raise
        except RuntimeError:
            raise
        except Exception as exc:
            logger.exception('E_commerce Payment Callback 失敗: merchant_trade_no=%s', merchant_trade_no)
            raise RuntimeError('E_commerce Payment Callback 失敗') from exc
        if not callback_result.get('success'):
            raise RuntimeError(f"商店處理失敗：{callback_result.get('message')}")
        with transaction.atomic():
            for field, value in payment_request_data.items():
                setattr(payment_request, field, value)
            payment_request.save(update_fields=list(payment_request_data.keys()))
            notification = PaymentNotification.objects.create(**notification_data)
            gateway_order = Order.objects.select_for_update().filter(order_number=merchant_trade_no).first()
            if gateway_order:
                gateway_order.status = 'paid' if is_paid else 'expired' if is_expired else 'failed'
                gateway_order.save(update_fields=['status', 'updated_at'])
        return {'status': True, 'message': '付款通知處理成功', 'payment': {'merchant_trade_no': merchant_trade_no, 'trade_no': str(trade_no), 'payment_status': normalized_payment_status, 'rtn_code': normalized_rtn_code, 'rtn_msg': notification.rtn_msg}, 'store_callback': callback_result}
    except Exception as exc:
        logger.exception('Payment notification 處理失敗: merchant_trade_no=%s', request_data.get('merchant_trade_no'))
        raise RuntimeError(f'付款通知處理失敗：{exc}') from exc
```

#### `ECPayService._notify_store_payment_result`（原檔第 299–459 行）
> 【新增】

```python
def _notify_store_payment_result(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(request_data, dict):
        raise ValueError('Store Payment Callback payload 必須是 dict')
    merchant_trade_no = request_data.get('merchant_trade_no')
    if not merchant_trade_no:
        raise ValueError('Store Payment Callback 缺少 merchant_trade_no')
    callback_payload = dict(request_data)
    callback_payload.pop('CheckMacValue', None)
    callback_payload.pop('check_mac_value', None)
    result = self.store_payment_gateway.notify_payment_result(callback_payload)
    if not isinstance(result, dict):
        raise RuntimeError('StorePaymentGateway 回傳格式錯誤')
    if not result.get('success'):
        logger.error('E_commerce Payment Callback 失敗：merchant_trade_no=%s, status_code=%s, message=%s', merchant_trade_no, result.get('status_code'), result.get('message'))
        raise RuntimeError('E_commerce Payment Callback 失敗')
    logger.info('E_commerce Payment Callback 成功：merchant_trade_no=%s, status_code=%s', merchant_trade_no, result.get('status_code'))
    return result
```

#### `ECPayService._ensure_gateway_order`（原檔第 2172–2206 行）

```python
def _ensure_gateway_order(self, request_data: Dict[str, Any], merchant_trade_no: str, amount):
    user_id = request_data.get('user_id')
    if user_id in (None, ''):
        logger.warning('ATM 缺少 user_id，略過建立 ecpay_mock Order：merchant_trade_no=%s', merchant_trade_no)
        return None
    order_obj, created = Order.objects.get_or_create(order_number=merchant_trade_no, defaults={'user_id': int(user_id), 'receiver_name': str(request_data.get('receiver_name') or ''), 'amount': amount, 'status': 'pending'})
    logger.info('ecpay_mock Order %s：merchant_trade_no=%s', '建立成功' if created else '已存在', merchant_trade_no)
    return order_obj
```

#### `ECPayService._build_atm_response`（原檔第 2325–2454 行）
> 【修改】

```python
def _build_atm_response(self, payment_request: PaymentRequest) -> Dict[str, Any]:
    try:
        if payment_request is None:
            raise RuntimeError('PaymentRequest 不存在')
        expire_date = getattr(payment_request, 'expire_date', None)
        if expire_date is not None:
            try:
                expire_date = expire_date.isoformat()
            except AttributeError:
                expire_date = str(expire_date)
        ecpay_mock_base_url = (getattr(settings, 'HF_SPACE_ECPAY_MOCK_URL', '') or '').rstrip('/')
        atm_info_url = f'{ecpay_mock_base_url}/gateway/atm_info/?merchant_trade_no={payment_request.merchant_trade_no}'
        return {'status': True, 'message': 'ATM 付款建立成功', 'atm_info_url': atm_info_url, 'payment': {'merchant_trade_no': str(payment_request.merchant_trade_no), 'trade_no': str(payment_request.trade_no), 'bank_code': str(payment_request.bank_code), 'v_account': str(payment_request.v_account), 'expire_date': expire_date, 'status': str(payment_request.status), 'check_mac_value': getattr(payment_request, 'check_mac_value', None)}}
    except RuntimeError:
        raise
    except Exception as exc:
        logger.exception('ATM Response 整理失敗')
        raise RuntimeError('ATM Response 整理失敗') from exc
```

#### `ECPayService.cancel_order`（原檔第 1269–1317 行）

```python
def cancel_order(self, *, merchant_trade_no: str) -> Dict[str, Any]:
    payment_request = PaymentRequest.objects.filter(merchant_trade_no=merchant_trade_no).first()
    if payment_request is None:
        raise LookupError('找不到 ATM 付款紀錄')
    if payment_request.status in ('atm_paid', 'atm_expired'):
        raise ValueError(f'此交易狀態為 {payment_request.status}，無法取消')
    self.ecpay_gateway.cancel_account(merchant_trade_no)
    with transaction.atomic():
        gateway_order = Order.objects.select_for_update().filter(order_number=merchant_trade_no).first()
        if gateway_order:
            gateway_order.status = 'cancelled'
            gateway_order.save(update_fields=['status', 'updated_at'])
        payment_request.status = 'atm_cancelled'
        payment_request.save(update_fields=['status'])
    return {'status': True, 'merchant_trade_no': merchant_trade_no, 'payment_status': 'atm_cancelled'}
```

### 📄 `ecpay_mock/cod_gateway/services/cod_service.py`

#### `CODService`（class，原檔第 26–336 行）

```python
class CODService:
    REQUIRED_FIELDS = ('merchant_trade_no', 'merchant_trade_date', 'user_id', 'trade_amt')
    ACTIONS = {'created': 'cod_created', 'shipped': 'cod_shipped', 'paid': 'cod_paid', 'failed': 'cod_failed', 'expired': 'cod_expired'}

    def __init__(self, store_gateway=None):
        self.store_gateway = store_gateway or CODStoreAdapter()

    @staticmethod
    def _new_trade_no():
        return 'EC' + uuid.uuid4().hex[:18].upper()

    @staticmethod
    def _parse_trade_date(raw):
        for fmt in ('%Y-%m-%d %H:%M:%S', '%Y/%m/%d %H:%M:%S'):
            try:
                value = datetime.strptime(str(raw), fmt)
                break
            except ValueError:
                continue
        else:
            raise ValueError('merchant_trade_date 格式錯誤')
        if settings.USE_TZ and timezone.is_naive(value):
            value = timezone.make_aware(value)
        return value

    def _notify_store(self, *, merchant_trade_no, trade_amt, status, trade_no, store_name='', store_address='', logistics_subtype='', simulate=False):
        payload = {'merchant_trade_no': merchant_trade_no, 'trade_amt': str(int(Decimal(str(trade_amt)))), 'status': status, 'payment_method': 'COD', 'provider_transaction_id': trade_no, 'trade_no': trade_no, 'cvs_store_name': store_name or '', 'cvs_store_address': store_address or '', 'logistics_subtype': logistics_subtype or '', 'payment_date': timezone.now().isoformat()}
        if simulate:
            payload['simulate'] = '1'
        result = self.store_gateway.notify_cod_status(payload)
        res_data = result['response_data']
        logger.info(f'res_data={dict(res_data)}')
        if not isinstance(result, dict) or not result.get('success'):
            message = result.get('message') if isinstance(result, dict) else result
            raise RuntimeError(f'商店處理失敗：{message}')
        return result

    def prepare_checkout(self, payment_data: Dict[str, Any]) -> Dict[str, str]:
        missing = [k for k in self.REQUIRED_FIELDS if not payment_data.get(k)]
        if missing:
            raise ValueError(f"缺少欄位: {', '.join(missing)}")
        try:
            amount = Decimal(str(payment_data['trade_amt']))
        except InvalidOperation as exc:
            raise ValueError('trade_amt 格式錯誤') from exc
        if amount <= 0:
            raise ValueError('trade_amt 必須大於 0')
        self._parse_trade_date(payment_data['merchant_trade_date'])
        return {'merchant_trade_no': str(payment_data['merchant_trade_no']), 'merchant_trade_date': str(payment_data['merchant_trade_date']), 'user_id': str(payment_data['user_id']), 'trade_amt': str(payment_data['trade_amt']), 'item_name': str(payment_data.get('item_name', '')), 'receiver_name': str(payment_data.get('receiver_name', '') or '王大明'), 'receiver_cell_phone': str(payment_data.get('receiver_cell_phone', '')), 'receiver_address': str(payment_data.get('receiver_address', '')), 'return_url': str(payment_data.get('ReturnURL', '')), 'order_result_url': str(payment_data.get('OrderResultURL', ''))}

    def confirm_store(self, *, checkout_data: Dict[str, str], store: Dict[str, Any]) -> CODPaymentRequest:
        if not checkout_data:
            raise ValueError('找不到結帳資料（session 已遺失），請重新從商城結帳')
        merchant_trade_no = checkout_data['merchant_trade_no']
        existing = CODPaymentRequest.objects.filter(merchant_trade_no=merchant_trade_no).first()
        trade_no = existing.trade_no if existing and existing.trade_no else self._new_trade_no()
        self._notify_store(merchant_trade_no=merchant_trade_no, trade_amt=checkout_data['trade_amt'], status='cod_confirmed', trade_no=trade_no, store_name=store['name'], store_address=store['address'], logistics_subtype=store['chain'])
        with transaction.atomic():
            order_obj, _ = Order.objects.get_or_create(order_number=merchant_trade_no, defaults={'user_id': int(checkout_data['user_id']), 'receiver_name': checkout_data['receiver_name'], 'amount': checkout_data['trade_amt'], 'status': 'pending'})
            cod_payment, _ = CODPaymentRequest.objects.update_or_create(merchant_trade_no=merchant_trade_no, defaults={'order': order_obj, 'merchant_trade_date': self._parse_trade_date(checkout_data['merchant_trade_date']), 'trade_no': trade_no, 'trade_amt': checkout_data['trade_amt'], 'item_name': checkout_data['item_name'], 'receiver_name': checkout_data['receiver_name'], 'receiver_cell_phone': checkout_data['receiver_cell_phone'], 'receiver_address': checkout_data['receiver_address'], 'status': 'cod_created', 'check_mac_value': checkout_data.get('check_mac_value', ''), 'return_url': checkout_data['return_url'], 'order_result_url': checkout_data['order_result_url'], 'logistics_subtype': store['chain'], 'store_id': store['store_id'], 'store_name': store['name'], 'store_address': store['address'], 'store_lat': store['lat'], 'store_lng': store['lng']})
        return cod_payment

    def cancel(self, merchant_trade_no: str) -> Dict[str, Any]:
        with transaction.atomic():
            cod = CODPaymentRequest.objects.select_for_update().filter(merchant_trade_no=merchant_trade_no).first()
            if cod is None:
                return {'status': True, 'merchant_trade_no': merchant_trade_no, 'cod_status': 'none'}
            if cod.status in ('cod_shipped', 'cod_paid', 'cod_expired'):
                raise ValueError(f'此訂單狀態為「{cod.get_status_display()}」，無法取消')
            cod.status = 'cod_cancelled'
            cod.save(update_fields=['status', 'updated_at'])
            order = cod.order
            order.status = 'cancelled'
            order.save()
        return {'status': True, 'merchant_trade_no': merchant_trade_no, 'cod_status': 'cod_cancelled'}

    def simulate(self, merchant_trade_no: str, action: str) -> Dict[str, Any]:
        if action not in self.ACTIONS:
            raise ValueError(f'未知的操作：{action}')
        target_status = self.ACTIONS[action]
        logger.info(f'action={action}')
        logger.info(f'target_status={target_status}')
        cod = CODPaymentRequest.objects.filter(merchant_trade_no=merchant_trade_no).first()
        if cod is None:
            raise LookupError('找不到該筆訂單編號')
        if cod.status == 'cod_cancelled':
            raise ValueError('此訂單已取消，無法模擬')
        if not cod.store_id:
            raise ValueError('此訂單尚未選定取貨門市')
        trade_no = cod.trade_no or self._new_trade_no()
        result = self._notify_store(merchant_trade_no=cod.merchant_trade_no, trade_amt=cod.trade_amt, status=target_status, trade_no=trade_no, store_name=cod.store_name, store_address=cod.store_address, logistics_subtype=cod.logistics_subtype, simulate=True)
        with transaction.atomic():
            cod = CODPaymentRequest.objects.select_for_update().get(merchant_trade_no=merchant_trade_no)
            cod.trade_no = trade_no
            cod.status = target_status
            cod.shipped_at = timezone.now() if action == 'shipped' else None
            cod.paid_at = timezone.now() if action == 'paid' else None
            cod.save()
            order = cod.order
            order.status = {'paid': 'paid', 'failed': 'failed', 'expired': 'expired'}.get(action, 'pending')
            order.save()
        return result
```

<a id="layer-6"></a>

## 6. 介面層 Interfaces（抽象 ABC）

ECPayService / CODService 只依賴這些抽象。

### 📄 `ecpay_mock/gateway/interface/ecpay_gateway.py`

#### `ECPayGateway`（class，原檔第 10–112 行）
> 【修改】

```python
class ECPayGateway(ABC):

    @abstractmethod
    def create_atm_payment(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def cancel_account(self, merchant_trade_no: str) -> Dict[str, Any]:
        pass

    @abstractmethod
    def query_payment(self, merchant_trade_no: str) -> Dict[str, Any]:
        raise NotImplementedError
```

### 📄 `ecpay_mock/gateway/interface/store_payment_gateway.py`

#### `StorePaymentNotifyResult`（class，原檔第 18–32 行）
> 【新增】

```python
@dataclass
class StorePaymentNotifyResult:
    success: bool
    status_code: int
    message: str
    response_data: Dict[str, Any]
```

#### `StorePaymentGateway`（class，原檔第 40–104 行）
> 【新增】

```python
class StorePaymentGateway(ABC):

    @abstractmethod
    def notify_payment_result(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError
```

### 📄 `ecpay_mock/cod_gateway/interface/cod_store_gateway.py`

#### `CODStoreGateway`（class，原檔第 9–17 行）
> 通知商店 COD 狀態。實作只能在 Adapter（httpx 只存在 Adapter）。

```python
class CODStoreGateway(ABC):

    @abstractmethod
    def notify_cod_status(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        ...
```

<a id="layer-7"></a>

## 7. 轉接層 Adapters（httpx）

→ Bank_site、→ E_commerce（ATM / COD）。

### 📄 `ecpay_mock/gateway/adapters/ecpay_mock_adapter.py`

#### `ECPayMockAdapter`（class，原檔第 25–723 行）
> 【本次修改】

```python
class ECPayMockAdapter(ECPayGateway):

    def __init__(self, timeout: float=10.0):
        try:
            self.timeout = timeout
            self.base_url = (getattr(settings, 'HF_SPACE_BANK_SITE_URL', '') or '').rstrip('/')
            if not self.base_url:
                raise RuntimeError('HF_SPACE_BANK_SITE_URL 未設定')
            self.create_account_url = f'{self.base_url}/notify/create_account/'
        except Exception as exc:
            logger.exception('ECPayMockAdapter 初始化失敗')
            raise RuntimeError('ECPayMockAdapter 初始化失敗') from exc

    def create_atm_payment(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            if not isinstance(payload, dict):
                raise ValueError('ATM payload 必須是 dict')
            merchant_trade_no = payload.get('merchant_trade_no')
            trade_amt = payload.get('trade_amt')
            if not merchant_trade_no:
                raise ValueError('缺少 merchant_trade_no')
            if trade_amt in (None, ''):
                raise ValueError('缺少 trade_amt')
            merchant_trade_no = str(merchant_trade_no)
            bank_payload = {'merchant_trade_no': merchant_trade_no, 'trade_amt': str(trade_amt), 'item_name': str(payload.get('item_name', '購買商品')), 'choose_payment': 'ATM'}
            hash_key = getattr(settings, 'ECPAY_HASH_KEY', '')
            hash_iv = getattr(settings, 'ECPAY_HASH_IV', '')
            if not hash_key or not hash_iv:
                raise RuntimeError('ECPAY_HASH_KEY / ECPAY_HASH_IV 未設定')
            try:
                bank_payload['CheckMacValue'] = generate_check_mac_value(bank_payload, hash_key, hash_iv)
            except Exception as exc:
                logger.exception('Bank Mock Request CheckMacValue 產生失敗')
                raise RuntimeError('Bank Mock CheckMacValue 產生失敗') from exc
            logger.info('Ecpay Mock → Bank Mock create_account: merchant_trade_no=%s', merchant_trade_no)
            try:
                response = httpx.post(self.create_account_url, json=bank_payload, timeout=self.timeout)
            except httpx.TimeoutException as exc:
                logger.exception('Bank Mock ATM API 逾時')
                raise RuntimeError('Bank Mock ATM API 逾時') from exc
            except httpx.RequestError as exc:
                logger.exception('Bank Mock ATM API 呼叫失敗')
                raise RuntimeError('Bank Mock ATM API 呼叫失敗') from exc
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                logger.exception('Bank Mock HTTP status error: %s', response.status_code)
                raise RuntimeError('Bank Mock HTTP 回應錯誤') from exc
            try:
                data = response.json()
            except ValueError as exc:
                logger.exception('Bank Mock 回傳非 JSON')
                raise RuntimeError('Bank Mock 回傳格式錯誤') from exc
            if not isinstance(data, dict):
                raise RuntimeError('Bank Mock 回傳資料必須是 dict')
            if not data.get('status'):
                raise ValueError(data.get('message', 'Bank Mock ATM 建立失敗'))
            payment_data = data.get('payment')
            if isinstance(payment_data, dict):
                result_data = payment_data
            else:
                result_data = data
            response_merchant_trade_no = result_data.get('merchant_trade_no')
            if not response_merchant_trade_no:
                raise RuntimeError('Bank Mock 回應缺少 merchant_trade_no')
            if str(response_merchant_trade_no) != merchant_trade_no:
                raise RuntimeError('Bank Mock merchant_trade_no 不一致')
            bank_code = result_data.get('bank_code')
            v_account = result_data.get('v_account')
            expire_date = result_data.get('expire_date')
            if not bank_code:
                raise RuntimeError('Bank Mock 回應缺少 bank_code')
            if not v_account:
                raise RuntimeError('Bank Mock 回應缺少 v_account')
            if not expire_date:
                raise RuntimeError('Bank Mock 回應缺少 expire_date')
            payment_status = result_data.get('payment_status')
            if not payment_status:
                raise RuntimeError('Bank Mock 回應缺少 payment_status')
            logger.info('Bank Mock ATM 建立成功: merchant_trade_no=%s, bank_code=%s, v_account=%s, payment_status=%sexpire_date=%s', merchant_trade_no, bank_code, v_account, payment_status, expire_date)
            return {'success': True, 'merchant_trade_no': str(response_merchant_trade_no), 'bank_code': str(bank_code), 'v_account': str(v_account), 'expire_date': expire_date, 'payment_status': str(payment_status), 'response_data': data}
        except ValueError:
            raise
        except RuntimeError:
            raise
        except Exception as exc:
            logger.exception('ECPayMockAdapter.create_atm_payment 發生未預期錯誤')
            raise RuntimeError('Bank Mock ATM 建立失敗') from exc

    def cancel_account(self, merchant_trade_no: str) -> Dict[str, Any]:
        bank_payload = {'merchant_trade_no': str(merchant_trade_no)}
        hash_key = getattr(settings, 'ECPAY_HASH_KEY', '')
        hash_iv = getattr(settings, 'ECPAY_HASH_IV', '')
        if not hash_key or not hash_iv:
            raise RuntimeError('ECPAY_HASH_KEY / ECPAY_HASH_IV 未設定')
        bank_payload['CheckMacValue'] = generate_check_mac_value(bank_payload, hash_key, hash_iv)
        url = f'{self.base_url}/notify/cancel_account/{merchant_trade_no}/'
        try:
            response = httpx.post(url, json=bank_payload, timeout=self.timeout)
        except httpx.TimeoutException as exc:
            logger.exception('Bank Mock 取消 ATM 逾時')
            raise RuntimeError('Bank Mock 取消 ATM 逾時') from exc
        except httpx.RequestError as exc:
            logger.exception('Bank Mock 取消 ATM 呼叫失敗')
            raise RuntimeError('Bank Mock 取消 ATM 呼叫失敗') from exc
        result = response.json() if response.content else {}
        if response.status_code >= 400 or not result.get('status'):
            raise RuntimeError(f"Bank Mock 取消 ATM 失敗：{result.get('message') or response.status_code}")
        return result

    def query_payment(self, merchant_trade_no: str) -> Dict[str, Any]:
        raise NotImplementedError('目前尚未定義 Bank Mock Payment Query endpoint')
```

### 📄 `ecpay_mock/gateway/adapters/store_payment_adapter.py`

#### `StorePaymentAdapter`（class，原檔第 39–392 行）
> 【新增】

```python
class StorePaymentAdapter(StorePaymentGateway):

    def __init__(self, callback_url: str | None=None, timeout: float | None=None) -> None:
        self.callback_url = callback_url or self._get_callback_url()
        self.timeout = timeout if timeout is not None else getattr(settings, 'STORE_PAYMENT_CALLBACK_TIMEOUT', 10.0)

    @staticmethod
    def _get_callback_url() -> str:
        configured_url = getattr(settings, 'STORE_PAYMENT_CALLBACK_URL', '')
        if configured_url:
            return configured_url.rstrip('/')
        ecommerce_url = getattr(settings, 'HF_SPACE_E_COMMERCE_URL', '')
        if not ecommerce_url:
            raise RuntimeError('缺少 STORE_PAYMENT_CALLBACK_URL 或 HF_SPACE_E_COMMERCE_URL')
        return ecommerce_url.rstrip('/') + '/commerce_shop/atm_payment_notify/'

    @staticmethod
    def _build_callback_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError('Store callback payload 必須是 dict')
        callback_payload = dict(payload)
        callback_payload.pop('CheckMacValue', None)
        callback_payload.pop('check_mac_value', None)
        check_mac_value = generate_check_mac_value(callback_payload, settings.ECPAY_HASH_KEY, settings.ECPAY_HASH_IV)
        callback_payload['CheckMacValue'] = check_mac_value
        return callback_payload

    def notify_payment_result(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not self.callback_url:
            raise RuntimeError('E_commerce payment callback URL 未設定')
        callback_payload = self._build_callback_payload(payload)
        logger.info('Ecpay Mock → E_commerce payment callback: %s', self.callback_url)
        try:
            response = httpx.post(self.callback_url, json=callback_payload, headers={'Content-Type': 'application/json'}, timeout=self.timeout)
        except httpx.RequestError as exc:
            logger.exception('Ecpay Mock → E_commerce callback HTTPX 失敗')
            return {'success': False, 'status_code': 0, 'message': 'E_commerce callback HTTPX request failed', 'response_data': {'error': str(exc)}}
        try:
            response_data = response.json()
            if not isinstance(response_data, dict):
                response_data = {'raw_response': response_data}
        except ValueError:
            response_data = {'raw_response': response.text}
        success = 200 <= response.status_code < 300
        if success:
            message = str(response_data.get('message', 'E_commerce callback success'))
        else:
            message = str(response_data.get('message', 'E_commerce callback failed'))
        return {'success': success, 'status_code': response.status_code, 'message': message, 'response_data': response_data}
```

### 📄 `ecpay_mock/cod_gateway/adapters/cod_store_adapter.py`

#### `CODStoreAdapter`（class，原檔第 19–88 行）

```python
class CODStoreAdapter(CODStoreGateway):

    def __init__(self):
        base_url = (getattr(settings, 'HF_SPACE_E_COMMERCE_URL', '') or '').rstrip('/')
        self.callback_url = f'{base_url}/commerce_shop/cod_payment_notify/'
        self.timeout = 10.0

    def notify_cod_status(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not self.callback_url.startswith('http'):
            raise RuntimeError('未設定 HF_SPACE_E_COMMERCE_URL')
        body = dict(payload)
        body.pop('CheckMacValue', None)
        body['CheckMacValue'] = generate_check_mac_value(body, settings.ECPAY_HASH_KEY, settings.ECPAY_HASH_IV)
        logger.info('ecpay_mock → E_commerce COD callback: %s', self.callback_url)
        try:
            response = httpx.post(self.callback_url, json=body, timeout=self.timeout)
        except httpx.RequestError as exc:
            logger.exception('COD callback HTTPX 失敗')
            return {'success': False, 'status_code': 0, 'message': f'商店連線失敗：{exc}', 'response_data': {}}
        try:
            data = response.json()
            if not isinstance(data, dict):
                data = {'raw_response': data}
        except ValueError:
            data = {'raw_response': response.text}
        success = 200 <= response.status_code < 300 and data.get('success') is not False
        return {'success': success, 'status_code': response.status_code, 'message': str(data.get('message', '') or ('商店處理成功' if success else '商店處理失敗')), 'response_data': data}
```

<a id="layer-8"></a>

## 8. 資料存取層 Repository

PaymentRequest / PaymentNotification 的 ORM 存取。

### 📄 `ecpay_mock/gateway/repositories/ecpay_repository.py`

#### `ECPayRepository`（class，原檔第 22–303 行）
> 【修改】

```python
class ECPayRepository:

    def get_by_merchant_trade_no(self, merchant_trade_no: str) -> Optional[PaymentRequest]:
        try:
            return PaymentRequest.objects.filter(merchant_trade_no=str(merchant_trade_no)).first()
        except Exception as exc:
            logger.exception('查詢 PaymentRequest 失敗: merchant_trade_no=%s', merchant_trade_no)
            raise RuntimeError('PaymentRequest 查詢失敗') from exc

    def create_payment_request(self, data: Dict[str, Any]) -> PaymentRequest:
        if not isinstance(data, dict):
            raise ValueError('PaymentRequest data 必須是 dict')
        if not data.get('merchant_trade_no'):
            raise ValueError('缺少 merchant_trade_no')
        try:
            with transaction.atomic():
                return PaymentRequest.objects.create(**data)
        except IntegrityError as exc:
            logger.warning('PaymentRequest 建立發生 IntegrityError，嘗試取得既有資料: merchant_trade_no=%s', data.get('merchant_trade_no'))
            try:
                existing = self.get_by_merchant_trade_no(data['merchant_trade_no'])
            except Exception as lookup_exc:
                logger.exception('IntegrityError 後重新查詢 PaymentRequest 失敗')
                raise RuntimeError('PaymentRequest 建立失敗') from lookup_exc
            if existing is not None:
                return existing
            raise RuntimeError('PaymentRequest 建立失敗') from exc
        except Exception as exc:
            logger.exception('PaymentRequest ORM 建立失敗')
            raise RuntimeError('PaymentRequest 建立失敗') from exc

    def update_payment_request(self, payment_request: PaymentRequest, data: Dict[str, Any]) -> PaymentRequest:
        if payment_request is None:
            raise ValueError('PaymentRequest 不存在')
        if not isinstance(data, dict):
            raise ValueError('PaymentRequest update data 必須是 dict')
        try:
            with transaction.atomic():
                for field, value in data.items():
                    setattr(payment_request, field, value)
                payment_request.save(update_fields=list(data.keys()) + ['updated_at'] if hasattr(payment_request, 'updated_at') else list(data.keys()))
            return payment_request
        except Exception as exc:
            logger.exception('PaymentRequest 更新失敗: merchant_trade_no=%s', getattr(payment_request, 'merchant_trade_no', None))
            raise RuntimeError('PaymentRequest 更新失敗') from exc

    def create_payment_notification(self, data: Dict[str, Any]) -> PaymentNotification:
        if not isinstance(data, dict):
            raise ValueError('PaymentNotification data 必須是 dict')
        required_fields = ('merchant_trade_no', 'trade_no', 'trade_amt', 'payment_date', 'choose_payment', 'payment_type', 'rtn_code', 'rtn_msg')
        for field in required_fields:
            if data.get(field) in (None, ''):
                raise ValueError(f'PaymentNotification 缺少 {field}')
        try:
            with transaction.atomic():
                return PaymentNotification.objects.create(**data)
        except Exception as exc:
            logger.exception('PaymentNotification 建立失敗: merchant_trade_no=%s', data.get('merchant_trade_no'))
            raise RuntimeError('PaymentNotification 建立失敗') from exc
```
