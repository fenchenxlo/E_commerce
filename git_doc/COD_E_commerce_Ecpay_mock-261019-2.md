# COD（貨到付款）模擬功能：E_commerce 與 Ecpay_mock 分層架構

> 依據 `1018-AI.zip` 內的實際檔案整理。本文聚焦 COD 模擬功能，不將 ATM 流程混入 COD。
> ZIP 內第二個專案的實際資料夾名稱是 `ecpay_mock/`（小寫），以下以「Ecpay_mock」稱呼。

## 1. 專案與功能範圍

- **E_commerce**：商城端。負責使用者訂單、收件資訊、付款方式選擇、COD 結帳資料準備、接收 Ecpay_mock 的狀態通知。
- **Ecpay_mock（資料夾 `ecpay_mock/`）**：模擬金流端。`cod_gateway` 負責 COD 門市選擇與貨到付款流程；`gateway` 是另一組 ECPay/ATM 相關功能，不能把它當成 COD 的主要入口。
- **COD 核心資料**：Ecpay_mock 的 `cod_gateway/models.py` 中有 `CODPaymentRequest`；商城訂單資料則在 E_commerce 的 `commerce_shop/models.py`。

## 2. 分層總覽

```text
使用者瀏覽器
  │
  ├─ E_commerce（商城）
  │   ├─ templates：商品／訂單／收件資訊頁面
  │   ├─ commerce_shop/urls.py
  │   ├─ commerce_shop/views.py
  │   │    ├─ 接收使用者操作
  │   │    ├─ 組合／驗證請求與回呼
  │   │    └─ COD callback：驗證 CheckMacValue 後交給 PaymentService
  │   ├─ commerce_shop/schemas/checkout.py：CheckoutSchema
  │   ├─ commerce_shop/services/order_service.py：OrderService
  │   │    └─ prepare_ecpay_cod_checkout()
  │   ├─ commerce_shop/services/payment_service.py：付款回呼處理
  │   ├─ commerce_shop/interfaces/ecpay_gateway.py：ECPayGateway 介面
  │   └─ commerce_shop/adapters/ecpay_mock_adapter.py：跨專案 HTTP 呼叫
  │
  └─ Ecpay_mock（實際目錄：ecpay_mock/）
      ├─ ecpay_mock/urls.py：專案路由掛載
      └─ cod_gateway（COD 模擬）
          ├─ urls.py
          ├─ views.py
          │    ├─ cod_checkout
          │    ├─ select_store / confirm_store / review_store
          │    ├─ mock_created / mock_shipped
          │    └─ simulate_cvscod_paid / failed / expired
          ├─ services/cod_service.py：CODService，業務驗證與流程協調
          ├─ interface/cod_store_gateway.py：通知商城的介面
          ├─ adapters/cod_store_adapter.py：實際 HTTP 通知
          ├─ models.py：CODPaymentRequest
          └─ templates：select_store、review_store、cod_info、cod_error
```

## 3. E_commerce：重要檔案與職責

| 層級 | 檔案 | COD 職責 |
|---|---|---|
| URL | `E_commerce/commerce_shop/urls.py` | 將商城頁面、結帳與通知 URL 對應到 view |
| View | `E_commerce/commerce_shop/views.py` | 接收使用者操作；`cod_payment_notify()` 接收 COD 模擬端回呼 |
| Schema | `E_commerce/commerce_shop/schemas/checkout.py` | 定義結帳請求資料結構（實際使用範圍以呼叫處為準） |
| Service | `E_commerce/commerce_shop/services/order_service.py` | `OrderService.prepare_ecpay_cod_checkout()` 檢查訂單並組合傳給模擬端的欄位 |
| Service | `E_commerce/commerce_shop/services/payment_service.py` | 處理付款／COD callback 的業務狀態更新 |
| Gateway Interface | `E_commerce/commerce_shop/interfaces/ecpay_gateway.py` | 定義商城端呼叫 ECPay 模擬服務的契約 |
| Adapter | `E_commerce/commerce_shop/adapters/ecpay_mock_adapter.py` | 實際 HTTP 請求與簽章等外部系統整合 |
| Model | `E_commerce/commerce_shop/models.py` | `Order`、`OrderItem`、`Payment` 等商城資料模型 |
| Template | `E_commerce/templates/` | 使用者操作頁面；應以實際 URL/view 的 render 或 redirect 關係確認頁面用途 |

### 3.1 COD 結帳資料準備：`OrderService.prepare_ecpay_cod_checkout()`

來源：`commerce_shop/services/order_service.py`

此方法會：
1. 依 `order_number` 與登入使用者查詢訂單，避免跨使用者操作訂單。
2. 要求訂單狀態為 `pending_payment`。
3. 要求 `payment_method == "COD"`。
4. 將訂單編號、金額、品項、收件人資訊與 `choose_payment="COD"` 組成資料，供後續模擬端使用。

```python
def prepare_ecpay_cod_checkout(self, user, order_number: str) -> Dict[str, Any]:
    order = (
        Order.objects
        .filter(order_number=order_number, user=user)
        .first()
    )
    if not order:
        raise ValueError("找不到訂單，或訂單不屬於目前使用者")
    if order.status != "pending_payment":
        raise ValueError(
            f"目前訂單狀態為 {order.status}，無法進行超商取貨付款"
        )
    if order.payment_method != "COD":
        raise ValueError("目前訂單付款方式不是 COD")

    item_names = "#".join(
        order.items.values_list("name", flat=True)
    ) or f"訂單 {order.order_number}"

    return {
        "merchant_trade_no": order.order_number,
        "merchant_trade_date": timezone.localtime(
            order.created_at
        ).strftime("%Y-%m-%d %H:%M:%S"),
        "user_id": user.id,
        "trade_amt": str(order.total_amount),
        "trade_desc": order.remark or "購買商品",
        "item_name": item_names,
        "payment_type": "aio",
        "choose_payment": "COD",
        "payment_method": "COD",
        "receiver_name": order.receiver_name or "",
        "receiver_cell_phone": order.receiver_phone or "",
        "receiver_address": order.receiver_address or "",
    }
```

> 上面為 ZIP 中方法的核心片段，為便於閱讀省略了後續欄位；完整實作仍以原始檔為準。

### 3.2 商城接收 COD 通知：`cod_payment_notify()`

來源：`commerce_shop/views.py`

重要安全順序：
1. 限制 POST。
2. 解析 JSON object。
3. 取出 `CheckMacValue`／`check_mac_value`。
4. 使用商城端 `ECPAY_HASH_KEY`、`ECPAY_HASH_IV` 重新計算簽章並比較。
5. 驗證通過後才呼叫 `PaymentService().handle_cod_callback(verify_payload)`。
6. 以 JSON 回應成功或錯誤。

核心程式：

```python
# 驗證一定在 Service 之前
verify_payload = dict(data)
received_mac = (
    verify_payload.pop("CheckMacValue", None)
    or verify_payload.pop("check_mac_value", None)
)
verify_payload.pop("check_mac_value", None)

if not received_mac:
    return JsonResponse(
        {"success": False, "message": "缺少 CheckMacValue"}, status=400
    )

expected_mac = generate_check_mac_value(
    verify_payload, settings.ECPAY_HASH_KEY, settings.ECPAY_HASH_IV
)

if not hmac.compare_digest(str(received_mac), str(expected_mac)):
    logger.warning("COD callback CheckMacValue 不一致")
    return JsonResponse(
        {"success": False, "message": "CheckMacValue Error"}, status=400
    )

result = PaymentService().handle_cod_callback(verify_payload)
```

## 4. Ecpay_mock：COD 分層

### 4.1 路由與 View

| 檔案 | 主要責任 |
|---|---|
| `ecpay_mock/urls.py` | 專案層 URL 設定與 app 路由掛載 |
| `cod_gateway/urls.py` | COD app 的 URL 名稱與 view 對應 |
| `cod_gateway/views.py` | HTTP 層：解析輸入、處理 session、選門市、呼叫 Service、render/redirect |
| `cod_gateway/templates/select_store.html` | 選擇模擬門市 |
| `cod_gateway/templates/review_store.html` | 確認門市／收件資料 |
| `templates/cod_info.html` | 顯示 COD 訂單／門市結果 |
| `templates/cod_error.html` | 顯示 COD 流程錯誤 |

`cod_gateway/views.py` 中可確認的主要函式包括：
- `cod_checkout`
- `select_store`
- `confirm_store`
- `review_store`
- `mock_created`
- `mock_shipped`
- `simulate_cvscod_paid`
- `simulate_cvscod_failed`
- `simulate_cvscod_expired`
- `cod_cancel`

### 4.2 Service：`CODService`

來源：`ecpay_mock/cod_gateway/services/cod_service.py`

主要方法與責任：
- `prepare_checkout(payment_data)`：檢查必要欄位、金額格式與交易日期，整理結帳資料。
- `confirm_store(checkout_data, store)`：確認門市、產生或沿用 `trade_no`、通知商城，並在通知成功後寫入 COD 模擬端資料。
- `cancel(...)`：處理取消流程。
- `simulate(...)`：支援模擬狀態變化。
- `_notify_store(...)`：透過 Gateway 通知商城；Service 不應自行承擔 HTTP adapter 細節。

`prepare_checkout()` 核心程式：

```python
def prepare_checkout(self, payment_data: Dict[str, Any]) -> Dict[str, str]:
    missing = [
        k for k in self.REQUIRED_FIELDS if not payment_data.get(k)
    ]
    if missing:
        raise ValueError(f"缺少欄位: {', '.join(missing)}")

    try:
        amount = Decimal(str(payment_data["trade_amt"]))
    except InvalidOperation as exc:
        raise ValueError("trade_amt 格式錯誤") from exc

    if amount <= 0:
        raise ValueError("trade_amt 必須大於 0")

    self._parse_trade_date(payment_data["merchant_trade_date"])
    return {
        "merchant_trade_no": str(payment_data["merchant_trade_no"]),
        "merchant_trade_date": str(payment_data["merchant_trade_date"]),
        "user_id": str(payment_data["user_id"]),
        "trade_amt": str(payment_data["trade_amt"]),
        "item_name": str(payment_data.get("item_name", "")),
        "receiver_name": str(payment_data.get("receiver_name", "") or "王大明"),
        "receiver_cell_phone": str(payment_data.get("receiver_cell_phone", "")),
        "receiver_address": str(payment_data.get("receiver_address", "")),
        "return_url": str(payment_data.get("ReturnURL", "")),
        "order_result_url": str(payment_data.get("OrderResultURL", "")),
    }
```

### 4.3 View 驗證簽章，再交給 Service

來源：`ecpay_mock/cod_gateway/views.py` 的 `cod_checkout()`

這個 View 的關鍵工作是驗證跨專案請求，而不是把全部業務邏輯寫在 View 裡：

```python
# Step 2：驗證 CheckMacValue
mac_a = payment_data.pop("CheckMacValue", "")
mac_b = payment_data.pop("check_mac_value", "")
received_mac = mac_a or mac_b
expected_mac = generate_check_mac_value(
    payment_data, settings.ECPAY_HASH_KEY, settings.ECPAY_HASH_IV
)

if not received_mac or not hmac.compare_digest(
    str(received_mac).upper(), str(expected_mac).upper()
):
    logger.warning("[cod_checkout] CheckMacValue 不符")
    return HttpResponse("CheckMacValue Error", status=400)

# Step 3：業務驗證交給 Service
checkout_data = CODService().prepare_checkout(payment_data)
checkout_data["check_mac_value"] = str(received_mac)
```

### 4.4 確認門市與資料一致性

來源：`cod_gateway/views.py` 的 `confirm_store()`、`cod_gateway/services/cod_service.py` 的 `confirm_store()`

流程重點：
1. View 從 session 取得 `cod_merchant_trade_no`。
2. 從 POST 取得 `store_id`，並確認它存在於模擬門市清單。
3. 若該交易已確認門市，直接顯示既有結果，避免重複建立。
4. 呼叫 `CODService.confirm_store()`。
5. Service 先通知商城 `cod_confirmed`；通知成功後才以交易資料更新 Ecpay_mock DB。
6. 產生／沿用 `trade_no`，讓同一筆交易重送時可保持一致。

核心片段：

```python
existing = CODPaymentRequest.objects.filter(
    merchant_trade_no=merchant_trade_no
).first()
if existing and existing.store_id:
    request.session.pop("cod_merchant_trade_no", None)
    request.session.pop("cod_checkout_data", None)
    return render(request, "cod_info.html", {
        "cod": existing,
        "HF_SPACE_E_COMMERCE_URL": settings.HF_SPACE_E_COMMERCE_URL,
    })

cod_payment = CODService().confirm_store(
    checkout_data=request.session.get("cod_checkout_data"),
    store=store,
)
```

Service 的順序（依原始實作）：

```python
# 先通知商店；失敗會丟 RuntimeError，後續 DB 不會執行
self._notify_store(
    merchant_trade_no=merchant_trade_no,
    trade_amt=checkout_data["trade_amt"],
    status="cod_confirmed",
    trade_no=trade_no,
    store_name=store["name"],
    store_address=store["address"],
    logistics_subtype=store["chain"],
)

# 商店成功後才寫 Ecpay_mock DB
with transaction.atomic():
    ...
```

## 5. Gateway / Adapter：跨專案通知

| 檔案 | 責任 |
|---|---|
| `cod_gateway/interface/cod_store_gateway.py` | 定義 `notify_cod_status(...)` 介面 |
| `cod_gateway/adapters/cod_store_adapter.py` | 實作介面，執行實際的商城 HTTP 通知 |
| `CODService._notify_store()` | 組織通知資料並透過 Gateway 呼叫 Adapter |

依專案分層設計，HTTP 傳輸細節應集中在 Adapter；View 不直接呼叫 HTTPX。實際 URL、timeout、簽章欄位與錯誤處理，請以 `cod_store_adapter.py` 原始內容為準。

## 6. COD 資料模型與狀態模擬

- `Ecpay_mock/cod_gateway/models.py`：`CODPaymentRequest`，保存模擬端 COD 交易資訊。
- `E_commerce/commerce_shop/models.py`：商城端 `Order`、`OrderItem`、`Payment` 等資料。
- COD 狀態模擬入口在 `cod_gateway/views.py`，包含 paid、failed、expired 等模擬函式；各狀態對資料庫的實際更新以 `CODService.simulate()` 及其呼叫內容為準。
- `cod_info.html` 是結果顯示頁，不應把 HTML 當作交易狀態的唯一資料來源。

## 7. COD 模擬功能頁面：畫面、按鈕與後端流程（補充重點）

本章專門補上「COD 模擬頁面實際能做什麼、每個按鈕會呼叫哪個 URL、後端由哪個 View／Service 處理」。這些頁面不只是交易結果展示；其中有使用者選店流程，也有管理員操作的 COD 狀態模擬面板。

### 6.1 COD 管理員模擬面板：`query_simulate_cod.html`

- **Template：** `ecpay_mock/templates/admin_tools/query_simulate_cod.html`
- **View：** `cod_gateway/views.py` 的 `query_and_simulate_cod()`
- **URL name：** `cod_gateway:query_and_simulate_cod`
- **進入路徑：** `ecpay_mock/urls.py` 將 `/` 轉址到此頁；依 app 路由設定，頁面也由 `cod_gateway` namespace 提供。
- **權限：** View 使用 `@user_passes_test(is_admin, login_url='/admin/login/')`，限定管理員。
- **頁面版面：** 左側為資料庫 Table／欄位查詢工具；右側為「模擬超商取貨付款」面板。

右側模擬面板要求輸入 `merchant_trade_no`，再選擇一個狀態操作：

| 畫面按鈕 | JS 操作值 | URL pattern（`cod_gateway/urls.py`） | 作用 |
|---|---|---|---|
| 模擬已取貨付款 | `paid` | `simulate_cvscod_paid/<merchant_trade_no>/` | 模擬顧客到超商取貨並付款 |
| 模擬取貨失敗未付款 | `failed` | `simulate_cvscod_failed/<merchant_trade_no>/` | 模擬取貨失敗／未付款 |
| 模擬逾期未付款 | `expired` | `simulate_cvscod_expired/<merchant_trade_no>/` | 模擬逾期未付款 |
| 模擬貨品已送達超商 | `shipped` | `mock_shipped/<merchant_trade_no>/` | 模擬貨物已送達門市，可進入取貨付款階段 |
| 模擬貨品未送達超商 | `created` | `mock_created/<merchant_trade_no>/` | 模擬交易仍在待出貨／尚未送達狀態 |

JavaScript `submitForm(type)` 會先檢查訂單編號是否為空，再依按鈕類型組出 URL，讀取 Django CSRF token，以 `fetch()` 發出 POST。回應預期為 JSON；前端會檢查 HTTP status、Content-Type 與 JSON 格式，並將成功／失敗訊息呈現給操作者。瀏覽器 Console 也會記錄操作類型、訂單編號、Request URL、HTTP 狀態與原始回應，方便除錯。

核心前端程式（摘錄自 `admin_tools/query_simulate_cod.html`）：

```javascript
function submitForm(type) {
    const input = document.getElementById('merchant_trade_no_input');
    const merchantTradeNo = input.value.trim();

    if (!merchantTradeNo) {
        alert('請先輸入訂單編號');
        return;
    }

    const encodedNo = encodeURIComponent(merchantTradeNo);
    let targetUrl = '';
    if (type === 'paid') {
        targetUrl = `/cod_gateway/simulate_cvscod_paid/${encodedNo}/`;
    } else if (type === 'failed') {
        targetUrl = `/cod_gateway/simulate_cvscod_failed/${encodedNo}/`;
    } else if (type === 'expired') {
        targetUrl = `/cod_gateway/simulate_cvscod_expired/${encodedNo}/`;
    } else if (type === 'shipped') {
        targetUrl = `/cod_gateway/mock_shipped/${encodedNo}/`;
    } else if (type === 'created') {
        targetUrl = `/cod_gateway/mock_created/${encodedNo}/`;
    } else {
        alert('未知的操作類型：' + type);
        return;
    }

    const csrfElement = document.querySelector('[name=csrfmiddlewaretoken]');
    // 後續以 fetch(targetUrl, {method: 'POST', headers: ...}) 發送請求
}
```

> 上方是關鍵路由分派摘錄；原始模板中還包含完整的 CSRF、回應文字、JSON 解析、錯誤處理與 Console 除錯程式，未在此重複貼出全部 JavaScript。

### 6.2 管理員模擬按鈕的後端呼叫鏈

```text
admin_tools/query_simulate_cod.html
  │ submitForm(type) + fetch(POST)
  ▼
cod_gateway/urls.py
  │ 對應 simulate_cvscod_paid / failed / expired / mock_shipped / mock_created
  ▼
cod_gateway/views.py
  │ 各 View 呼叫 _run_simulation(request, merchant_trade_no, action, label)
  ▼
CODService.simulate(merchant_trade_no, action)
  │
  ├─ 找不到交易 → JSON 404
  ├─ 狀態／輸入不合法 → JSON 400
  ├─ 通知商城或處理失敗 → JSON 500，並回報 Ecpay_mock 未更新
  └─ 成功 → JSON 200，回報已同步通知商城
```

`_run_simulation()` 是這組模擬按鈕共用的 View helper：

```python
def _run_simulation(request, merchant_trade_no, action, label):
    try:
        CODService().simulate(merchant_trade_no, action)
    except LookupError:
        return JsonResponse(
            {"status": "failed", "message": "找不到該筆訂單編號"}, status=404
        )
    except ValueError as ex:
        return JsonResponse({"status": "failed", "message": str(ex)}, status=400)
    except Exception as ex:
        logger.exception(f"[simulate:{action}] 訂單 {merchant_trade_no} 失敗")
        return JsonResponse(
            {"status": "failed", "message": f"{label}失敗，ecpay 未更新：{ex}"},
            status=500,
        )

    msg = f"訂單 {merchant_trade_no}「{label}」成功，已同步通知商店！"
    messages.success(request, msg)
    return JsonResponse({"status": "success", "message": msg}, status=200)
```

### 6.3 COD 使用者選店頁：`select_store.html`

- **Template：** `ecpay_mock/templates/select_store.html`
- **View：** `select_store()`
- **前置條件：** `cod_checkout()` 已驗證商城送來的 CheckMacValue，並將 `cod_merchant_trade_no` 與 `cod_checkout_data` 暫存於 session。
- **畫面功能：** 顯示模擬超商清單與地圖；使用者可點選清單或地圖標記選取門市。選取後更新隱藏欄位 `store_id`，並啟用「確認選擇此門市」按鈕。
- **下一步：** POST 至 `cod_gateway:review_store`，進入門市確認頁；此時尚未正式建立 COD DB 記錄，也尚未通知商城。
- **錯誤處理：** session 沒有訂單編號時回傳可讀的錯誤，而非直接在模板中發生例外。

### 6.4 門市確認頁：`review_store.html`

- **Template：** `ecpay_mock/templates/review_store.html`
- **View：** `review_store()`
- **畫面功能：** 顯示所選門市名稱、地址及訂單資訊，讓使用者再次核對。
- **「確認無誤，送出」：** POST 到 `cod_gateway:confirm_store`。這一步才真正進入 `CODService.confirm_store()`，通知商城並在通知成功後寫入 Ecpay_mock 的 COD 記錄。
- **「重新選擇門市」：** GET 回 `cod_gateway:select_store`。
- **重要設計：** `review_store()` 只從 session 讀取結帳資料，使用 `SimpleNamespace` 提供模板所需屬性；使用者停留在確認頁或返回重選時，不會先寫入一筆尚未確認的 COD 記錄。

### 6.5 COD 結果頁：`cod_info.html` 與錯誤頁 `cod_error.html`

- **`cod_info.html`：** 顯示 COD 交易資料、取貨門市名稱／地址與動態訂單狀態（使用 `cod.get_status_display`），並提供返回商城訂單頁的連結。
- **`cod_error.html`：** 顯示門市確認或跨專案通知失敗原因，提供返回商城訂單頁的操作入口。
- **注意：** 結果頁只是呈現後端資料；實際交易狀態由 `CODService`、`CODPaymentRequest` 及跨專案通知決定，不能只靠畫面文字判斷付款成功。

### 6.6 COD 狀態模擬與狀態名稱

`cod_gateway/services/cod_service.py` 的 `ACTIONS` 對應如下：

| 模擬操作 | Service action | Ecpay_mock COD 狀態 |
|---|---|---|
| 尚未送達／待出貨 | `created` | `cod_created` |
| 已送達超商 | `shipped` | `cod_shipped` |
| 已取貨付款 | `paid` | `cod_paid` |
| 取貨失敗／未付款 | `failed` | `cod_failed` |
| 逾期未付款 | `expired` | `cod_expired` |
| 取消 | `cancel`（由 `CODService.cancel()` 處理） | `cod_cancelled` |

模擬操作會透過 `_notify_store()`／Gateway／Adapter 將狀態同步至商城。若通知失敗，Service 會讓呼叫端知道錯誤，避免前端單純顯示「成功」而 Ecpay_mock 與 E_commerce 的資料狀態不一致。取消另有 `cod_cancel/` endpoint，不能把它與「逾期未付款」當成相同狀態。

---

## 8. 端到端流程

```text
1. 使用者在 E_commerce 選擇 COD 並提交收件資料
   ↓
2. E_commerce 的 View / OrderService
   - 確認訂單屬於目前使用者
   - 確認訂單 pending_payment
   - 確認 payment_method = COD
   - 準備 merchant_trade_no、金額、收件資料
   ↓
3. E_commerce Adapter 將已簽章的請求送到 Ecpay_mock COD endpoint
   ↓
4. Ecpay_mock cod_checkout View
   - 解析請求
   - 驗證 CheckMacValue
   - 呼叫 CODService.prepare_checkout()
   - 將交易資訊放入 session，進入門市選擇流程
   ↓
5. 使用者選擇／確認模擬門市
   ↓
6. confirm_store View → CODService.confirm_store()
   - 防止重複確認
   - 通知 E_commerce：cod_confirmed
   - 通知成功後保存 Ecpay_mock COD 記錄
   ↓
7. Ecpay_mock 顯示 cod_info.html
   ↓
8. 後續模擬建立、出貨、付款成功／失敗／逾期／取消
   - 依各 simulate/cancel endpoint 與 Service 實作更新狀態
   - 需要同步商城狀態時，透過 Gateway / Adapter 通知商城
```

## 9. 重要檔案快速索引

### E_commerce
- `commerce_shop/urls.py`
- `commerce_shop/views.py`
- `commerce_shop/services/order_service.py`
- `commerce_shop/services/payment_service.py`
- `commerce_shop/schemas/checkout.py`
- `commerce_shop/interfaces/ecpay_gateway.py`
- `commerce_shop/adapters/ecpay_mock_adapter.py`
- `commerce_shop/models.py`

### Ecpay_mock（ZIP 內目錄為 `ecpay_mock/`）
- `ecpay_mock/urls.py`
- `cod_gateway/urls.py`
- `cod_gateway/views.py`（包含 `query_and_simulate_cod()`、`_run_simulation()` 與各狀態模擬 View）
- `cod_gateway/services/cod_service.py`
- `cod_gateway/interface/cod_store_gateway.py`
- `cod_gateway/adapters/cod_store_adapter.py`
- `cod_gateway/models.py`
- `templates/select_store.html`
- `templates/review_store.html`
- `templates/cod_info.html`
- `templates/cod_error.html`
- `templates/admin_tools/query_simulate_cod.html`（管理員 COD 狀態模擬面板）

## 10. 維護時的分層界線

1. **View**：處理 HTTP、session、request parsing、回應與頁面導向；避免把整段業務流程塞進 View。
2. **Service**：處理 COD 規則、狀態轉換、交易資料與流程協調。
3. **Interface**：描述 Service 需要的外部能力，不負責 HTTP 傳輸。
4. **Adapter**：處理 HTTPX、外部 URL、timeout、傳輸錯誤與必要的請求簽章。
5. **Model**：保存交易／訂單資料，不代替跨專案通知流程。
6. **Template**：顯示資料與提供操作入口，不應直接承擔付款狀態判斷。
7. **簽章驗證**：跨專案入口必須在進入業務處理前驗證 `CheckMacValue`。
8. **重送與冪等**：以 `merchant_trade_no` 查詢既有資料、沿用既有 `trade_no`，避免重送造成重複交易。
9. **通知與資料庫順序**：目前 `confirm_store()` 的程式採「先通知商城、通知成功後才寫 Ecpay_mock DB」；若日後要調整，需特別考量兩個專案間無法共用單一 DB transaction 的一致性風險。
10. **狀態名稱需一致**：商城端與模擬端狀態字串可能不同；新增狀態時應同時核對 callback、Service、Model choices 與頁面顯示。

## 11. 閱讀限制與核對提醒

- 本文件是根據 `1018-AI.zip` 中可見的程式檔整理，並非對執行中服務的整合測試報告。
- ZIP 內同時有 `ecpay_mock/gateway/`（ECPay／ATM 相關）與 `ecpay_mock/cod_gateway/`（COD 相關）。追 COD 流程時，應優先從 `cod_gateway/` 進入。
- `E_commerce` 的 `views.py` 很大，包含多種付款與管理功能；請用本文列出的函式名稱與檔案路徑定位，不要將所有 view 都視為 COD 專用。
- 如要將文件用於下一階段修改，應再次核對當前工作目錄是否已與 ZIP 版本同步。
