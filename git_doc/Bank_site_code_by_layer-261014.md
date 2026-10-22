# Bank_site（模擬銀行）— 分層重要程式碼

> **閱讀說明**：本文件由原始碼自動擷取（AST），只保留「重要流程的程式碼」，已移除 docstring 與註解並重新排版（縮排、引號可能與原檔略有不同），僅供閱讀與理解架構；實際修改請以原始檔為準。每段標題附有原檔行號。
> 擷取來源：`E-Shop_Api_1012.zip`（2026-10-14 最新版）：含取消訂單、ATM 取消守衛、刪除同步、金額重算。

## 專案定位
模擬銀行端（Django + SQLite，HF Space），只有一個 app `notify`，只處理 **ATM** 虛擬帳號（COD 不會到這裡）。

## 呼叫關係
```
ecpay_mock ──► notify/views ──► BankAccountService ──► BankAccountGateway(interface) ──► BankAccountAdapter
                                                                  └─ notify_ecpay_mock ──httpx──► ecpay_mock /gateway/payment_notify/
```

## 功能
- `create_account/`：建立虛擬帳號（bank_code=013、有效 3 天）
- `simulate_paid / simulate_failed / simulate_expired`：後台模擬 → 先通知 ecpay_mock，成功才寫 Bank DB
- `cancel_account/`：ecpay_mock 呼叫的取消入口（Bank 為鏈尾，直接寫 DB；已付款 / 已逾期不可取消）

## VirtualAccount.status
pending / cod_created / atm_created / unpaid / paid / expired / cancelled


---

## 目錄

1. [路由層 Routing](#layer-1)
2. [資料模型層 Models](#layer-2)
3. [入口層 Views](#layer-3)
4. [服務層 Services（商業邏輯）](#layer-4)
5. [介面層 Interfaces（抽象 ABC）](#layer-5)
6. [轉接層 Adapters（MAC / httpx）](#layer-6)

---

<a id="layer-1"></a>

## 1. 路由層 Routing

專案與 notify 路由。

### 📄 `Bank_site/Bank_site/urls.py`

```python
from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView
urlpatterns = [
    path('', RedirectView.as_view(pattern_name='notify:query_and_simulate', permanent=False), name='root_redirect'),
    path('admin/', admin.site.urls),
    path('notify/', include('notify.urls')),
]
```

### 📄 `Bank_site/notify/urls.py`

```python
from django.urls import path, include
from notify.views import home, create_account, account_detail, simulate_paid, simulate_failed, simulate_expired, cancel_account, db_query_tool, query_and_simulate
app_name = 'notify'
urlpatterns = [
    path('', home, name='home'),
    path('create_account/', create_account, name='create_account'),
    path('account_detail/<str:merchant_trade_no>/', account_detail, name='account_detail'),
    path('simulate_paid/<str:merchant_trade_no>/', simulate_paid, name='simulate_paid'),
    path('simulate_failed/<str:merchant_trade_no>/', simulate_failed, name='simulate_failed'),
    path('simulate_expired/<str:merchant_trade_no>/', simulate_expired, name='simulate_expired'),
    path('cancel_account/<str:merchant_trade_no>/', cancel_account, name='cancel_account'),
    path('admin-tools/db_query_tool/', db_query_tool, name='db_query_tool'),
    path('admin-tools/query_and_simulate/', query_and_simulate, name='query_and_simulate'),
]
```

<a id="layer-2"></a>

## 2. 資料模型層 Models

VirtualAccount。

### 📄 `Bank_site/notify/models.py`

#### `VirtualAccount`（class，原檔第 6–61 行）
> 銀行端收到綠界通知後建立的虛擬帳號資料

```python
class VirtualAccount(models.Model):
    merchant_trade_no = models.CharField(max_length=50, unique=True)
    bank_code = models.CharField(max_length=3, null=True, blank=True)
    v_account = models.CharField(max_length=20, unique=True, null=True, blank=True)
    trade_amt = models.DecimalField(max_digits=10, decimal_places=2)
    expire_date = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=[('pending', 'Pending'), ('cod_created', 'COD_Created'), ('atm_created', 'ATM Created'), ('unpaid', 'Unpaid'), ('paid', 'Paid'), ('expired', 'Expired'), ('cancelled', 'Cancelled')], default='atm_created')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.merchant_trade_no
```

<a id="layer-3"></a>

## 3. 入口層 Views

收 request / 回 JSON，不碰 ORM。

### 📄 `Bank_site/notify/views.py`

#### `get_bank_account_service`（def，原檔第 233–254 行）
> 建立 BankAccountService。

```python
def get_bank_account_service():
    gateway = BankAccountAdapter()
    service = BankAccountService(gateway=gateway)
    return service
```

#### `create_account`（def，原檔第 281–550 行）
> 建立 ATM 虛擬帳號。

```python
@csrf_exempt
def create_account(request):
    if request.method != 'POST':
        return JsonResponse({'status': False, 'message': '只允許 POST'}, status=405)
    try:
        if not request.body:
            return JsonResponse({'status': False, 'message': 'Request body 不可為空'}, status=400)
        data = json.loads(request.body.decode('utf-8'))
    except json.JSONDecodeError:
        logger.warning('Bank Mock create_account 收到無效 JSON')
        return JsonResponse({'status': False, 'message': 'JSON 格式錯誤'}, status=400)
    except UnicodeDecodeError:
        logger.warning('Bank Mock create_account 收到無效 UTF-8')
        return JsonResponse({'status': False, 'message': 'Request Body 編碼錯誤'}, status=400)
    if not isinstance(data, dict):
        return JsonResponse({'status': False, 'message': 'Request JSON 必須是 Object'}, status=400)
    received_check_mac_value = data.get('CheckMacValue')
    if not received_check_mac_value:
        logger.warning('Bank Mock create_account 缺少 CheckMacValue')
        return JsonResponse({'status': False, 'message': '缺少 CheckMacValue'}, status=400)
    verify_data = data.copy()
    verify_data.pop('CheckMacValue', None)
    expected_check_mac_value = generate_check_mac_value(verify_data, settings.ECPAY_HASH_KEY, settings.ECPAY_HASH_IV)
    if received_check_mac_value != expected_check_mac_value:
        logger.warning('Bank Mock create_account CheckMacValue 驗證失敗')
        return JsonResponse({'status': False, 'message': 'CheckMacValue 驗證失敗'}, status=400)
    merchant_trade_no = data.get('merchant_trade_no')
    trade_amt = data.get('trade_amt')
    data['bank_code'] = '013'
    data['v_account'] = f'013{random.randint(100000000000, 999999999999)}'
    data['expire_date'] = (datetime.datetime.now() + datetime.timedelta(days=3)).strftime('%Y-%m-%d %H:%M:%S')
    logging.info('bank_code=%s', data['bank_code'])
    logging.info('v_account=%s', data['v_account'])
    logging.info('expire_date=%s', data['expire_date'])
    if not merchant_trade_no:
        return JsonResponse({'status': False, 'message': '缺少 merchant_trade_no'}, status=400)
    if trade_amt in (None, ''):
        return JsonResponse({'status': False, 'message': '缺少 trade_amt'}, status=400)
    service = get_bank_account_service()
    try:
        logger.info('data：%s', data)
        result = service.create_account(merchant_trade_no=merchant_trade_no, trade_amt=trade_amt, request_data=data)
    except ValueError as ex:
        logger.warning('Bank Mock create_account 業務驗證失敗：%s', ex)
        return JsonResponse({'status': False, 'message': str(ex)}, status=400)
    except Exception as ex:
        logger.exception('Bank Mock create_account 發生未預期錯誤')
        return JsonResponse({'status': False, 'message': 'Bank Mock 建立虛擬帳號失敗', 'error': str(ex)}, status=500)
    return JsonResponse(result, status=200)
```

#### `account_detail`（def，原檔第 557–667 行）
> 顯示 ATM 虛擬帳號。

```python
def account_detail(request, merchant_trade_no):
    if request.method != 'GET':
        return JsonResponse({'status': False, 'message': '只允許 GET'}, status=405)
    service = get_bank_account_service()
    try:
        result = service.get_account(merchant_trade_no=merchant_trade_no)
    except LookupError:
        return JsonResponse({'status': False, 'message': '找不到 ATM 虛擬帳號'}, status=404)
    except ValueError as ex:
        return JsonResponse({'status': False, 'message': str(ex)}, status=400)
    except Exception as ex:
        logger.exception('Bank Mock account_detail 發生錯誤')
        return JsonResponse({'status': False, 'message': '查詢 ATM 虛擬帳號失敗', 'error': str(ex)}, status=500)
    return render(request, 'account_detail.html', {'account': result})
```

#### `simulate_paid`（def，原檔第 675–793 行）
> 模擬 ATM 付款成功。

```python
@csrf_exempt
def simulate_paid(request, merchant_trade_no):
    if request.method not in ('GET', 'POST'):
        return JsonResponse({'status': False, 'message': '只允許 GET 或 POST'}, status=405)
    service = get_bank_account_service()
    try:
        result = service.simulate_paid(merchant_trade_no=merchant_trade_no)
    except LookupError:
        return JsonResponse({'status': False, 'message': '找不到 ATM 虛擬帳號'}, status=404)
    except ValueError as ex:
        logger.warning('Bank Mock simulate_paid 業務錯誤：%s', ex)
        return JsonResponse({'status': False, 'message': str(ex)}, status=400)
    except Exception as ex:
        logger.exception('Bank Mock simulate_paid 發生未預期錯誤')
        return JsonResponse({'status': False, 'message': '模擬付款成功失敗', 'error': str(ex)}, status=500)
    return JsonResponse(result, status=200)
```

#### `simulate_failed`（def，原檔第 801–910 行）
> 模擬 ATM 付款失敗。

```python
@csrf_exempt
def simulate_failed(request, merchant_trade_no):
    if request.method not in ('GET', 'POST'):
        return JsonResponse({'status': False, 'message': '只允許 GET 或 POST'}, status=405)
    service = get_bank_account_service()
    try:
        result = service.simulate_failed(merchant_trade_no=merchant_trade_no)
    except LookupError:
        return JsonResponse({'status': False, 'message': '找不到 ATM 虛擬帳號'}, status=404)
    except ValueError as ex:
        logger.warning('Bank Mock simulate_failed 業務錯誤：%s', ex)
        return JsonResponse({'status': False, 'message': str(ex)}, status=400)
    except Exception as ex:
        logger.exception('Bank Mock simulate_failed 發生未預期錯誤')
        return JsonResponse({'status': False, 'message': '模擬付款失敗', 'error': str(ex)}, status=500)
    return JsonResponse(result, status=200)
```

#### `simulate_expired`（def，原檔第 923–955 行）

```python
@csrf_exempt
def simulate_expired(request, merchant_trade_no):
    if request.method not in ('GET', 'POST'):
        return JsonResponse({'status': False, 'message': '只允許 GET 或 POST'}, status=405)
    service = get_bank_account_service()
    try:
        result = service.simulate_expired(merchant_trade_no=merchant_trade_no)
    except LookupError:
        return JsonResponse({'status': False, 'message': '找不到 ATM 虛擬帳號'}, status=404)
    except ValueError as ex:
        logger.warning('Bank Mock simulate_expired 業務錯誤：%s', ex)
        return JsonResponse({'status': False, 'message': str(ex)}, status=400)
    except Exception as ex:
        logger.exception('Bank Mock simulate_expired 發生未預期錯誤')
        return JsonResponse({'status': False, 'message': '模擬逾期未付款失敗', 'error': str(ex)}, status=500)
    return JsonResponse(result, status=200)
```

#### `cancel_account`（def，原檔第 964–1005 行）

```python
@csrf_exempt
def cancel_account(request, merchant_trade_no):
    if request.method != 'POST':
        return JsonResponse({'status': False, 'message': '只允許 POST'}, status=405)
    try:
        data = json.loads(request.body or b'{}')
    except json.JSONDecodeError:
        return JsonResponse({'status': False, 'message': 'JSON 格式錯誤'}, status=400)
    service = get_bank_account_service()
    try:
        result = service.cancel_account(merchant_trade_no=merchant_trade_no, request_data=data)
    except LookupError:
        return JsonResponse({'status': False, 'message': '找不到 ATM 虛擬帳號'}, status=404)
    except ValueError as ex:
        logger.warning('Bank Mock cancel_account 業務錯誤：%s', ex)
        return JsonResponse({'status': False, 'message': str(ex)}, status=400)
    except Exception as ex:
        logger.exception('Bank Mock cancel_account 發生未預期錯誤')
        return JsonResponse({'status': False, 'message': '取消 ATM 帳號失敗', 'error': str(ex)}, status=500)
    return JsonResponse(result, status=200)
```

<a id="layer-4"></a>

## 4. 服務層 Services（商業邏輯）

建立帳號、查詢、三種模擬、取消。

### 📄 `Bank_site/notify/services/bank_account_service.py`

#### `BankAccountService`（class，原檔第 17–859 行）
> Bank Mock ATM 業務 Service。

```python
class BankAccountService:

    def __init__(self, gateway):
        if gateway is None:
            raise ValueError('BankAccountService 必須提供 gateway')
        self.gateway = gateway

    def create_account(self, merchant_trade_no: str, trade_amt, request_data: dict) -> dict:
        if not merchant_trade_no:
            raise ValueError('merchant_trade_no 不可為空')
        if trade_amt is None:
            raise ValueError('trade_amt 不可為空')
        try:
            logger.info('request_data：%s', request_data)
            bank_code = request_data.get('bank_code')
            v_account = request_data.get('v_account')
            expire_date = request_data.get('expire_date')
            status = request_data.get('status')
            if not bank_code:
                raise ValueError('bank_code 不可為空')
            if not v_account:
                raise ValueError('v_account 不可為空')
            if not expire_date:
                raise ValueError('expire_date 不可為空')
            expire_datetime = parse_datetime(str(expire_date))
            if expire_datetime is None:
                raise ValueError('expire_date 格式錯誤')
            if timezone.is_naive(expire_datetime):
                expire_datetime = timezone.make_aware(expire_datetime)
            virtual_account, created = VirtualAccount.objects.get_or_create(merchant_trade_no=merchant_trade_no, defaults={'bank_code': bank_code, 'v_account': v_account, 'trade_amt': trade_amt, 'expire_date': expire_datetime, 'status': 'atm_created'})
            logger.info('VirtualAccount %s：merchant_trade_no=%s', '建立成功' if created else '已存在，直接取得', virtual_account.merchant_trade_no)
            result = {'success': True, 'status': 'created' if created else 'existing', 'message': 'ATM 虛擬帳號建立成功' if created else 'ATM 虛擬帳號已存在', 'merchant_trade_no': virtual_account.merchant_trade_no, 'bank_code': virtual_account.bank_code, 'v_account': virtual_account.v_account, 'trade_amt': str(virtual_account.trade_amt), 'expire_date': virtual_account.expire_date.isoformat() if virtual_account.expire_date else None, 'payment_status': virtual_account.status}
        except ValueError:
            raise
        except Exception as ex:
            logger.exception('Bank Mock 建立 ATM 虛擬帳號失敗')
            raise RuntimeError('Bank Mock 建立 ATM 虛擬帳號失敗') from ex
        if not result:
            raise RuntimeError('Bank Mock 沒有回傳 ATM 資訊')
        return result

    def get_account(self, merchant_trade_no: str):
        if not merchant_trade_no:
            raise ValueError('merchant_trade_no 不可為空')
        try:
            account = VirtualAccount.objects.get(merchant_trade_no=merchant_trade_no)
        except VirtualAccount.DoesNotExist as ex:
            raise LookupError('找不到 ATM 虛擬帳號') from ex
        except Exception as ex:
            logger.exception('Bank Mock 查詢 ATM 帳號失敗')
            raise RuntimeError('Bank Mock 查詢 ATM 帳號失敗') from ex
        return account

    def simulate_paid(self, merchant_trade_no: str) -> dict:
        account = self.get_account(merchant_trade_no)
        if account.status == 'cancelled':
            raise ValueError('此 ATM 帳號已取消，無法模擬付款')
        if account.status == 'paid':
            raise ValueError('此 ATM 帳號已經付款完成')
        try:
            result = self.gateway.notify_ecpay_mock(account=account, payment_status='paid')
        except Exception as ex:
            logger.exception('Bank Mock → ECPay Mock 付款成功 callback 失敗')
            raise RuntimeError('通知 ECPay Mock 付款成功失敗') from ex
        if not result.get('status'):
            raise RuntimeError(f"ECPay Mock 處理失敗，Bank 未更新：{result.get('response') or result.get('message')}")
        try:
            with transaction.atomic():
                account = VirtualAccount.objects.select_for_update().get(merchant_trade_no=merchant_trade_no)
                if account.status == 'paid':
                    raise ValueError('此 ATM 帳號已經付款完成')
                account.status = 'paid'
                account.save(update_fields=['status'])
        except ValueError:
            raise
        except VirtualAccount.DoesNotExist as ex:
            logger.exception('找不到 Bank Mock ATM 帳號：merchant_trade_no=%s', merchant_trade_no)
            raise LookupError('找不到 ATM 虛擬帳號') from ex
        except Exception as ex:
            logger.exception('Bank Mock 更新 ATM 付款狀態失敗')
            raise RuntimeError('Bank Mock 更新 ATM 付款狀態失敗') from ex
        return result

    def simulate_failed(self, merchant_trade_no: str) -> dict:
        account = self.get_account(merchant_trade_no)
        if account.status == 'cancelled':
            raise ValueError('此 ATM 帳號已取消，無法模擬付款失敗')
        try:
            result = self.gateway.notify_ecpay_mock(account=account, payment_status='atm_failed')
        except Exception as ex:
            logger.exception('Bank Mock → ECPay Mock 付款失敗 callback 失敗')
            raise RuntimeError('通知 ECPay Mock 付款失敗失敗') from ex
        if not result.get('status'):
            raise RuntimeError(f"ECPay Mock 處理失敗，Bank 未更新：{result.get('response') or result.get('message')}")
        try:
            with transaction.atomic():
                account = VirtualAccount.objects.select_for_update().get(merchant_trade_no=merchant_trade_no)
                account.status = 'unpaid'
                account.save(update_fields=['status'])
        except VirtualAccount.DoesNotExist as ex:
            logger.exception('找不到 Bank Mock ATM 帳號：merchant_trade_no=%s', merchant_trade_no)
            raise LookupError('找不到 ATM 虛擬帳號') from ex
        except Exception as ex:
            logger.exception('Bank Mock 更新 ATM 付款失敗狀態失敗')
            raise RuntimeError('Bank Mock 更新 ATM 付款失敗狀態失敗') from ex
        return result

    def cancel_account(self, merchant_trade_no: str, request_data: dict) -> dict:
        self.gateway.verify_check_mac_value(request_data)
        account = self.get_account(merchant_trade_no)
        if account.status in ('paid', 'expired'):
            raise ValueError(f'此 ATM 帳號狀態為 {account.status}，無法取消')
        account.status = 'cancelled'
        account.save(update_fields=['status'])
        return {'status': True, 'merchant_trade_no': merchant_trade_no, 'account_status': 'cancelled'}

    def simulate_expired(self, merchant_trade_no: str) -> dict:
        account = self.get_account(merchant_trade_no)
        if account.status == 'expired':
            raise ValueError('此 ATM 帳號已經逾期，不需重複模擬')
        if account.status == 'cancelled':
            raise ValueError('此 ATM 帳號已取消，無法模擬逾期')
        try:
            result = self.gateway.notify_ecpay_mock(account=account, payment_status='atm_expired')
        except Exception as ex:
            logger.exception('Bank Mock → ECPay Mock 逾期 callback 失敗')
            raise RuntimeError('通知 ECPay Mock 逾期未付款失敗') from ex
        if not result.get('status'):
            raise RuntimeError(f"ECPay Mock 處理失敗，Bank 未更新：{result.get('response') or result.get('message')}")
        try:
            with transaction.atomic():
                account = VirtualAccount.objects.select_for_update().get(merchant_trade_no=merchant_trade_no)
                account.status = 'expired'
                account.save(update_fields=['status'])
        except VirtualAccount.DoesNotExist as ex:
            raise LookupError('找不到 ATM 虛擬帳號') from ex
        except Exception as ex:
            logger.exception('Bank Mock 更新 ATM 逾期狀態失敗')
            raise RuntimeError('Bank Mock 更新 ATM 逾期狀態失敗') from ex
        return result
```

<a id="layer-5"></a>

## 5. 介面層 Interfaces（抽象 ABC）

Service 只依賴此抽象。

### 📄 `Bank_site/notify/interfaces/bank_account_gateway.py`

#### `BankAccountGateway`（class，原檔第 10–229 行）
> 【本次修改】

```python
class BankAccountGateway(ABC):

    @abstractmethod
    def create_virtual_account(self, merchant_trade_no: str, trade_amt: Decimal, request_data: dict) -> dict:
        raise NotImplementedError

    @abstractmethod
    def get_virtual_account(self, merchant_trade_no: str):
        raise NotImplementedError

    @abstractmethod
    def update_account_status(self, account, status: str):
        raise NotImplementedError

    @abstractmethod
    def verify_check_mac_value(self, request_data):
        pass

    @abstractmethod
    def notify_ecpay_mock(self, account, payment_status: str) -> dict:
        raise NotImplementedError

    @abstractmethod
    def build_account_response(self, account) -> dict:
        raise NotImplementedError
```

<a id="layer-6"></a>

## 6. 轉接層 Adapters（MAC / httpx）

CheckMacValue 驗證、虛擬帳號產生、通知 ecpay_mock。

### 📄 `Bank_site/notify/adapters/bank_account_adapter.py`

#### `BankAccountAdapter`（class，原檔第 33–1177 行）
> 【本次修改】

```python
class BankAccountAdapter(BankAccountGateway):

    def __init__(self):
        self.bank_code = getattr(settings, 'BANK_MOCK_BANK_CODE', '013')
        self.expire_days = getattr(settings, 'BANK_MOCK_EXPIRE_DAYS', 3)
        self.ecpay_mock_url = getattr(settings, 'ECPAY_MOCK_PAYMENT_NOTIFY_URL', '')
        if not self.ecpay_mock_url:
            ecpay_mock_base_url = getattr(settings, 'HF_SPACE_ECPAY_MOCK_URL', '')
            if ecpay_mock_base_url:
                self.ecpay_mock_url = f"{ecpay_mock_base_url.rstrip('/')}/gateway/payment_notify/"

    def verify_check_mac_value(self, request_data):
        return self._verify_check_mac_value(request_data)

    def _verify_check_mac_value(self, request_data):
        if request_data is None:
            logger.debug('Bank Mock create_virtual_account 未提供 request_data，略過外部 MAC 驗證')
            return True
        if not isinstance(request_data, dict):
            logger.warning('Bank Mock request_data 格式錯誤：不是 dict')
            raise ValueError('request_data 必須是 dict')
        if 'CheckMacValue' not in request_data:
            logger.warning('Bank Mock 收到請求但缺少 CheckMacValue')
            raise ValueError('缺少 CheckMacValue')
        received_mac = request_data.get('CheckMacValue')
        if not received_mac:
            logger.warning('Bank Mock 收到空的 CheckMacValue')
            raise ValueError('CheckMacValue 不可為空')
        payload = dict(request_data)
        payload.pop('CheckMacValue', None)
        hash_key = getattr(settings, 'ECPAY_HASH_KEY', '')
        hash_iv = getattr(settings, 'ECPAY_HASH_IV', '')
        if not hash_key:
            logger.error('Bank Mock 未設定 ECPAY_HASH_KEY')
            raise RuntimeError('未設定 ECPAY_HASH_KEY')
        if not hash_iv:
            logger.error('Bank Mock 未設定 ECPAY_HASH_IV')
            raise RuntimeError('未設定 ECPAY_HASH_IV')
        try:
            expected_mac = generate_check_mac_value(payload, hash_key, hash_iv)
        except Exception as ex:
            logger.exception('Bank Mock CheckMacValue 計算失敗')
            raise RuntimeError('CheckMacValue 計算失敗') from ex
        if not hmac.compare_digest(str(received_mac).upper(), str(expected_mac).upper()):
            logger.warning('Bank Mock CheckMacValue 驗證失敗')
            raise ValueError('CheckMacValue 驗證失敗')
        logger.debug('Bank Mock CheckMacValue 驗證成功')
        return True

    def _generate_virtual_account(self):
        random_number = random.randint(100000000000, 999999999999)
        return f'{self.bank_code}{random_number}'

    def _generate_expire_date(self):
        return timezone.now() + timedelta(days=self.expire_days)

    def create_virtual_account(self, merchant_trade_no: str, trade_amt: Decimal, request_data=None) -> dict:
        if not merchant_trade_no:
            logger.warning('Bank Mock 建立 ATM 時缺少 merchant_trade_no')
            raise ValueError('merchant_trade_no 不可為空')
        if trade_amt is None:
            logger.warning('Bank Mock 建立 ATM 時缺少 trade_amt')
            raise ValueError('trade_amt 不可為空')
        try:
            trade_amt = Decimal(str(trade_amt))
        except Exception as ex:
            logger.warning('Bank Mock trade_amt 格式錯誤：%s', ex)
            raise ValueError(f'trade_amt 格式錯誤: {ex}') from ex
        if trade_amt <= 0:
            logger.warning('Bank Mock trade_amt 必須大於 0：trade_amt=%s', trade_amt)
            raise ValueError('trade_amt 必須大於 0')
        self._verify_check_mac_value(request_data)
        try:
            existing_account = VirtualAccount.objects.filter(merchant_trade_no=merchant_trade_no).first()
        except Exception as ex:
            logger.exception('Bank Mock 查詢既有 VirtualAccount 失敗')
            raise RuntimeError('查詢 Bank Mock ATM 帳號失敗') from ex
        if existing_account:
            if existing_account.trade_amt != trade_amt:
                logger.warning('Bank Mock 發現相同 merchant_trade_no 但 trade_amt 不一致：merchant_trade_no=%s existing_trade_amt=%s request_trade_amt=%s', merchant_trade_no, existing_account.trade_amt, trade_amt)
                raise ValueError('相同 merchant_trade_no 的付款金額不一致')
            logger.info('Bank Mock 重用既有 ATM：merchant_trade_no=%s', merchant_trade_no)
            return self.build_account_response(existing_account)
        bank_code = self.bank_code
        expire_date = self._generate_expire_date()
        virtual_account = None
        for attempt in range(1, 6):
            v_account = self._generate_virtual_account()
            try:
                with transaction.atomic():
                    virtual_account = VirtualAccount.objects.create(merchant_trade_no=merchant_trade_no, bank_code=bank_code, v_account=v_account, trade_amt=trade_amt, expire_date=expire_date, status='atm_created')
                logger.info('Bank Mock ATM 建立成功：merchant_trade_no=%s attempt=%s', merchant_trade_no, attempt)
                break
            except IntegrityError as ex:
                try:
                    existing_account = VirtualAccount.objects.filter(merchant_trade_no=merchant_trade_no).first()
                except Exception as query_ex:
                    logger.exception('Bank Mock IntegrityError 後，重新查詢 merchant_trade_no 失敗')
                    raise RuntimeError('檢查 Bank Mock ATM 重複資料失敗') from query_ex
                if existing_account:
                    if existing_account.trade_amt != trade_amt:
                        raise ValueError('相同 merchant_trade_no 的付款金額不一致')
                    logger.info('Bank Mock concurrent request 已建立 ATM，直接重用：merchant_trade_no=%s', merchant_trade_no)
                    virtual_account = existing_account
                    break
                logger.warning('Bank Mock ATM 建立 IntegrityError，可能是 v_account collision：merchant_trade_no=%s attempt=%s error=%s', merchant_trade_no, attempt, ex)
                continue
            except Exception as ex:
                logger.exception('Bank Mock 建立 VirtualAccount 失敗：merchant_trade_no=%s', merchant_trade_no)
                raise RuntimeError('建立 Bank Mock ATM 帳號失敗') from ex
        if virtual_account is None:
            logger.error('Bank Mock 無法產生唯一 ATM 虛擬帳號：merchant_trade_no=%s', merchant_trade_no)
            raise RuntimeError('無法產生唯一的 ATM 虛擬帳號')
        return self.build_account_response(virtual_account)

    def build_account_response(self, account) -> dict:
        if account is None:
            raise ValueError('VirtualAccount 不可為空')
        trade_amt = str(int(account.trade_amt))
        return {'status': True, 'merchant_trade_no': account.merchant_trade_no, 'bank_code': account.bank_code, 'v_account': account.v_account, 'trade_amt': trade_amt, 'expire_date': account.expire_date.strftime('%Y-%m-%d %H:%M:%S'), 'payment_status': account.status}

    def get_virtual_account(self, merchant_trade_no: str):
        if not merchant_trade_no:
            logger.warning('Bank Mock 查詢 ATM 時缺少 merchant_trade_no')
            raise ValueError('merchant_trade_no 不可為空')
        try:
            return VirtualAccount.objects.get(merchant_trade_no=merchant_trade_no)
        except VirtualAccount.DoesNotExist:
            logger.info('Bank Mock 找不到 VirtualAccount：merchant_trade_no=%s', merchant_trade_no)
            return None
        except Exception as ex:
            logger.exception('Bank Mock 取得 VirtualAccount 失敗：merchant_trade_no=%s', merchant_trade_no)
            raise RuntimeError('取得 Bank Mock ATM 帳號失敗') from ex

    def update_account_status(self, account, status: str):
        allowed_statuses = {'atm_created', 'unpaid', 'paid', 'expired'}
        if status not in allowed_statuses:
            logger.warning('Bank Mock 收到不允許的 ATM status：%s', status)
            raise ValueError(f'不允許的 ATM status: {status}')
        try:
            account.status = status
            account.save(update_fields=['status'])
            logger.info('Bank Mock ATM 狀態更新成功：merchant_trade_no=%s status=%s', account.merchant_trade_no, status)
            return account
        except Exception as ex:
            logger.exception('Bank Mock 更新 ATM 狀態失敗：merchant_trade_no=%s status=%s', getattr(account, 'merchant_trade_no', None), status)
            raise RuntimeError('更新 Bank Mock ATM 狀態失敗') from ex

    def notify_ecpay_mock(self, account, payment_status: str) -> dict:
        if not self.ecpay_mock_url:
            logger.error('Bank Mock 未設定 ECPay Mock callback URL')
            raise RuntimeError('未設定 ECPAY_MOCK_PAYMENT_NOTIFY_URL')
        payload = {'merchant_trade_no': account.merchant_trade_no, 'trade_amt': str(int(account.trade_amt)), 'bank_code': account.bank_code, 'v_account': account.v_account, 'expire_date': account.expire_date.strftime('%Y-%m-%d %H:%M:%S'), 'status': payment_status, 'simulate': '1'}
        try:
            payload['CheckMacValue'] = generate_check_mac_value(payload, settings.ECPAY_HASH_KEY, settings.ECPAY_HASH_IV)
        except Exception as ex:
            logger.exception('Bank Mock callback CheckMacValue 產生失敗：merchant_trade_no=%s', account.merchant_trade_no)
            raise RuntimeError('產生 ECPay Mock callback MAC 失敗') from ex
        try:
            logger.info('self.ecpay_mock_url=%s', self.ecpay_mock_url)
            response = httpx.post(self.ecpay_mock_url, json=payload, timeout=10.0)
        except httpx.TimeoutException as ex:
            logger.exception('Bank Mock → ECPay Mock timeout：merchant_trade_no=%s', account.merchant_trade_no)
            return {'status': False, 'message': 'ECPay Mock callback timeout', 'error_type': type(ex).__name__}
        except httpx.RequestError as ex:
            logger.exception('Bank Mock → ECPay Mock HTTP request error：merchant_trade_no=%s', account.merchant_trade_no)
            return {'status': False, 'message': str(ex), 'error_type': type(ex).__name__}
        except Exception as ex:
            logger.exception('Bank Mock → ECPay Mock 發生未知錯誤：merchant_trade_no=%s', account.merchant_trade_no)
            return {'status': False, 'message': str(ex), 'error_type': type(ex).__name__}
        if response.status_code != 200:
            logger.error('ECPay Mock callback HTTP 失敗：merchant_trade_no=%s status_code=%s response=%s', account.merchant_trade_no, response.status_code, response.text)
            return {'status': False, 'message': 'ECPay Mock callback 失敗', 'status_code': response.status_code, 'response': response.text}
        try:
            response_data = response.json()
        except ValueError:
            logger.error('ECPay Mock callback HTTP 200，但回傳不是合法 JSON：merchant_trade_no=%s response=%s', account.merchant_trade_no, response.text)
            return {'status': False, 'message': 'ECPay Mock 回傳格式錯誤', 'response': response.text}
        if not isinstance(response_data, dict):
            logger.error('ECPay Mock callback HTTP 200，但 JSON 不是 Object：merchant_trade_no=%s response=%s', account.merchant_trade_no, response_data)
            return {'status': False, 'message': 'ECPay Mock callback 回傳格式錯誤', 'response': response_data}
        gateway_status = response_data.get('status')
        if gateway_status is None:
            gateway_status = response_data.get('success')
        is_business_success = gateway_status is True or str(gateway_status).strip().lower() in {'true', 'success', 'ok', '1'}
        if not is_business_success:
            logger.warning('ECPay Mock callback HTTP 200，但 business status 失敗：merchant_trade_no=%s gateway_status=%s response=%s', account.merchant_trade_no, gateway_status, response_data)
            return {'status': False, 'message': 'ECPay Mock callback business status 失敗', 'gateway_response': response_data}
        logger.info('Bank Mock → ECPay Mock callback 成功：merchant_trade_no=%s payment_status=%s', account.merchant_trade_no, payment_status)
        return {'status': True, 'gateway_response': response_data}
```
