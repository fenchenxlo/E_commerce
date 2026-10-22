# ATM 模擬功能：E_commerce、Ecpay_mock、Bank_site 分層與重要程式碼

> 原始依據：使用者提供的 `1018-AI.zip`。本文整理 ZIP 中實際存在的檔案與程式，不把建議流程當成已實作功能。程式片段保留原始內容；為方便閱讀，部分片段只截取關鍵區段，檔案路徑與行號以 ZIP 版本為準。

## 1. 三個專案的責任總覽

| 專案 | ATM 主要責任 | 主要入口／頁面 | 主要資料 |
|---|---|---|---|
| `E_commerce` | 商城訂單、收件資料、選擇 ATM、建立 checkout payload、接收付款回呼並更新商城訂單／付款狀態 | `commerce_shop/views.py`、`templates` | `Order`、`Payment`、`OrderItem` 等商城資料 |
| `ecpay_mock`（即 Ecpay_mock） | 模擬金流服務；接收商城請求、驗證 CheckMacValue、向 Bank Mock 申請虛擬帳號、保存金流資料、顯示 ATM 資訊、接收銀行通知 | `gateway/views.py`、`gateway/services/ecpay_service.py`、`templates/atm_info.html` | `gateway/models.py` 中的付款請求／通知資料 |
| `Bank_site` | 模擬銀行端 ATM 虛擬帳號、到期日與狀態；提供查詢、模擬付款成功／失敗／逾期／取消；通知 Ecpay Mock | `notify/views.py`、`notify/services/bank_account_service.py`、`notify/adapters/bank_account_adapter.py` | `notify/models.py` 的 `VirtualAccount` |

### 1.1 核心跨專案呼叫鏈

```text
使用者
  │ 選擇 ATM、填寫收件資料
  ▼
E_commerce / commerce_shop/views.py
  │ ecpay_checkout_redirect
  ▼
OrderService.prepare_ecpay_atm_checkout()
  │ 組成 payload（訂單編號、金額、商品、回呼 URL 等）
  ▼
E_commerce ECPayGateway
  ▼
E_commerce ECPayMockAdapter ── HTTPX ──► Ecpay_mock /gateway/ecpay_gateway_checkout/
                                            │ View 邊界驗證 CheckMacValue
                                            ▼
                                      ECPayService.create_atm_payment()
                                            ▼
                                      Ecpay_mock ECPayGateway
                                            ▼
                                      ECPayMockAdapter ── HTTPX ──► Bank_site /notify/create_account/
                                                                        │
                                                                        ▼
                                                              BankAccountService / Gateway / Adapter
                                                                        │ 建立 VirtualAccount
                                                                        ▼
Ecpay_mock 收到 bank_code、v_account、expire_date ◄────────────────────┘
  │ 建立金流端付款資料並呈現 ATM 資訊
  ▼
使用者於 Bank Mock 模擬付款／失敗／逾期
  ▼
BankAccountService → BankAccountGateway → BankAccountAdapter
  │ HTTPX 通知 Ecpay_mock /gateway/payment_notify/
  ▼
Ecpay_mock View → ECPayService.process_payment_notification()
  │ 更新金流狀態／通知商城
  ▼
E_commerce /commerce_shop/atm_payment_notify/
  │ PaymentService.handle_atm_callback()
  ▼
更新商城 Payment、Order 及相關庫存／保留資料
```

> 上圖是依現有入口、Service、Gateway/Adapter 職責整理的概念呼叫鏈。實際部署 URL 仍受各專案 `settings.py` 的環境變數影響。

## 2. E_commerce：商城端分層

### 2.1 主要檔案索引

| 層級 | 檔案 | 責任 |
|---|---|---|
| URL | `E_commerce/commerce_shop/urls.py` | 將 ATM checkout、付款回呼、訂單頁路由到 View |
| View | `E_commerce/commerce_shop/views.py` | HTTP 請求／回應、登入使用者、接收 callback、轉交 Service |
| Service | `E_commerce/commerce_shop/services/order_service.py` | 驗證訂單歸屬與狀態、組合 ATM payload |
| Service | `E_commerce/commerce_shop/services/payment_service.py` | ATM callback、付款狀態、取消與庫存處理等付款業務邏輯 |
| Interface | `E_commerce/commerce_shop/interfaces/ecpay_gateway.py` | 定義商城呼叫 Ecpay Mock 的契約 |
| Adapter | `E_commerce/commerce_shop/adapters/ecpay_mock_adapter.py` | 對外 HTTPX 呼叫及協定資料處理 |
| Schema | `E_commerce/commerce_shop/schemas/checkout.py` 等 | 驗證 checkout 輸入資料（依具體入口使用） |
| Model | `E_commerce/commerce_shop/models.py` | 訂單、付款及商品明細等資料模型 |
| Template | `E_commerce/E_commerce/templates/`、專案其他 templates 目錄 | 顯示訂單、收件資料及 ATM 資訊／導轉表單 |

### 2.2 ATM checkout 入口路由

來源：`E_commerce/commerce_shop/urls.py`

```python
path(
    "atm_payment_notify/",
    atm_payment_notify,
    name="atm_payment_notify",
),
path(
    "ecpay_checkout_redirect/",
    ecpay_checkout_redirect,
    name="ecpay_checkout_redirect",
),
path(
    "enter_receiver_info/<str:order_number>/",
    enter_receiver_info,
    name="enter_receiver_info",
),
path(
    "purchased_products/",
    purchased_products,
    name="purchased_products",
),
```

### 2.3 `OrderService.prepare_ecpay_atm_checkout()`：建立商城端 ATM payload

來源：`E_commerce/commerce_shop/services/order_service.py`。此方法依現有程式碼先查詢目前使用者的訂單，再檢查訂單狀態及付款方式；它負責準備 payload，不直接呼叫 HTTPX 或 Bank Mock。

```python
    def prepare_ecpay_atm_checkout(
        self,
        user,
        order_number: str,
    ) -> Dict[str, Any]:
        """
        【新增】

        準備 Browser → Ecpay Mock 所需要的 ATM payload。

        流程：

            ecpay_checkout_redirect View
                    ↓
            OrderService
                    ↓
            取得目前使用者自己的 Order
                    ↓
            建立 ECPay payload
                    ↓
            回傳 payload 給 View

        注意：

            這裡只負責準備付款資料。

            不建立 Payment。
            不呼叫 ECPayGateway。
            不呼叫 HTTPX。
            不呼叫 Bank Mock。
        """

        if not order_number:
            raise ValueError(
                "缺少 order_number"
            )

        try:

            # ====================================================
            # 【新增】
            # 取得目前登入使用者自己的 Order。
            #
            # 這裡直接依照目前專案實際使用的
            # Django ORM 查詢方式取得 Order。
            # ====================================================

            order = (
                Order.objects
                .filter(
                    order_number=order_number,
                    user=user,
                )
                .first()
            )

            if not order:
                raise ValueError(
                    "找不到訂單，或訂單不屬於目前使用者"
                )

            # ====================================================
            # 【新增】
            # 只能對尚未付款的訂單建立 ATM Checkout。
            # ====================================================

            if order.status != "pending_payment":
                raise ValueError(
                    f"目前訂單狀態為 {order.status}，"
                    "無法進行 ATM 付款"
                )

            # ====================================================
            # 【新增】
            # 必須確認付款方式已經由
            # enter_receiver_info.html
```

### 2.4 `ECPayGateway`：商城端的介面契約

來源：`E_commerce/commerce_shop/interfaces/ecpay_gateway.py`

```python

# ============================================================
# commerce_shop/interfaces/ecpay_gateway.py
# ============================================================

from abc import ABC, abstractmethod
from typing import Any, Dict


class ECPayGateway(ABC):
    """
    ECPay Gateway Interface。

    【新增】

    Service 只依賴這個 Interface。

    實際 HTTPX：
        ECPayMockAdapter

    Service：
        不知道 HTTPX
        不知道 CheckMacValue 實作細節
        不知道 ECPay Mock URL

    """

    # ========================================================
    # 【保留】
    # ATM 建立
    # ========================================================

    @abstractmethod
    def create_atm_payment(
        self,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        建立 ATM 付款流程。

        payload：
            Store 業務資料。

        return：
            ECPay Mock 回應結果。
        """
        raise NotImplementedError

    # ========================================================
    # 【保留】
    # Payment Query
    # ========================================================

    # 【修改】取消交易（E_commerce → ECPay Mock）：原 cancel_atm_payment，
    # 加 payment_method 參數同時支援 ATM / COD
    @abstractmethod
    def cancel_payment(
        self,
        merchant_trade_no: str,
        payment_method: str = "ATM",
        delete_record: bool = False,   # 【新增】True=通知下游刪除已取消的紀錄
    ) -> Dict[str, Any]:
        pass

    @abstractmethod
    def query_payment(
        self,
        merchant_trade_no: str,
    ) -> Dict[str, Any]:
        """
        查詢付款狀態。

        【保留】

        這個能力不能因為目前先做 ATM 建立，
        就被刪除。

        實際 HTTPX：
            ECPayMockAdapter
        """
        raise NotImplementedError

```

### 2.5 ATM callback 與付款狀態處理

來源：`E_commerce/commerce_shop/views.py` 的 `atm_payment_notify()`，以及 `E_commerce/commerce_shop/services/payment_service.py` 的 `handle_atm_callback()`。View 接收外部回呼，Service 負責依付款結果處理商城資料。

重要方法索引：

- `commerce_shop/views.py::atm_payment_notify`（約第 531 行起）
- `commerce_shop/services/payment_service.py::handle_atm_callback`（約第 1031 行起）
- `commerce_shop/services/payment_service.py::cancel_order`（約第 1754 行起）
- `commerce_shop/services/payment_service.py::delete_downstream_records`（約第 1821 行起）
- `commerce_shop/services/order_service.py::mark_order_paid`（約第 1078 行起）
- `commerce_shop/services/order_service.py::release_order_inventory`（約第 1223 行起）

```python
def atm_payment_notify(request):
    """
    【修改】

    ECPay Mock → Store ATM callback。

    View 只負責：

        1. HTTP Method
        2. 解析 request
        3. 驗證 CheckMacValue
        4. 呼叫 PaymentService
        5. 回傳 HTTP Response

    View 不負責：

        ❌ Order.objects
        ❌ Payment.objects
        ❌ Payment.save()
        ❌ httpx.post()
        ❌ ATM 產生
        ❌ 庫存處理
        ❌ Payment business logic

    Flow：

        ECPay Mock
              ↓
        atm_payment_notify
              ↓
        CheckMacValue verify
              ↓
        PaymentService
              ↓
        PaymentRepository
              ↓
        Payment
    """

    # ============================================================
    # 【新增】
    # HTTP Method
    # ============================================================

    if request.method != "POST":

        return JsonResponse(
            {
                "status": False,
                "success": False,
                "message": "Method Not Allowed",
            },
            status=405,
        )

    # ============================================================
    # 【新增】
    # Request Parse
    # ============================================================

    try:

        # --------------------------------------------------------
        # JSON
```

> 回呼的實際驗簽、狀態映射與資料更新，請以 `handle_atm_callback()` 的完整方法為準；不能只憑 View 名稱推定每個狀態都已完成整合測試。

## 3. Ecpay_mock：模擬金流端分層

### 3.1 主要檔案索引

| 層級 | 檔案 | 責任 |
|---|---|---|
| URL | `ecpay_mock/gateway/urls.py` | 金流 checkout、ATM 資訊、付款通知、取消及模擬頁入口 |
| View | `ecpay_mock/gateway/views.py` | 解析 request、驗證商城送來的 CheckMacValue、呼叫 Service、渲染頁面／回應 callback |
| Service | `ecpay_mock/gateway/services/ecpay_service.py` | 建立 ATM 付款、保存 PaymentRequest、處理銀行付款通知與通知商城 |
| Service | `ecpay_mock/gateway/services/payment_service.py` | 較通用的付款操作與查詢能力；需依實際呼叫點辨認用途 |
| Interface | `ecpay_mock/gateway/interface/ecpay_gateway.py` | 定義 Ecpay Mock 呼叫 Bank Mock 的介面 |
| Adapter | `ecpay_mock/gateway/adapters/ecpay_mock_adapter.py` | Ecpay Mock → Bank Mock 的 HTTPX 請求 |
| Adapter | `ecpay_mock/gateway/adapters/store_payment_adapter.py` | Ecpay Mock → E_commerce 的付款通知／外部呼叫適配器 |
| Schema | `ecpay_mock/gateway/schemas/checkout.py` | checkout payload 結構驗證 |
| Model | `ecpay_mock/gateway/models.py` | 金流端付款請求與通知資料 |
| Template | `ecpay_mock/templates/atm_info.html`、`atm_payment.html`、`ecpay_atm_info.html` | ATM 資訊與模擬付款頁面模板；實際使用哪個由 View 的 render 呼叫決定 |

### 3.2 正式 ATM 入口與回呼路由

來源：`ecpay_mock/gateway/urls.py`

```python
path("ecpay_gateway_checkout/", ecpay_gateway_checkout, name="ecpay_gateway_checkout"),
path("simulate_bank_paid/", simulate_bank_paid, name="simulate_bank_paid"),
path("payment_info/", payment_info, name="payment_info"),
path("atm_info/", atm_info, name="atm_info"),
path("payment_notify/", payment_notify, name="payment_notify"),
path("cancel_order/", cancel_order, name="cancel_order"),
```

`ecpay_gateway_checkout/` 是目前 URL 設定中正式 ATM 建立入口；舊 `checkout/`、`pay/`、`notify/` 等路由在此檔案中以註解保留，不是啟用中的正式 URL pattern。

### 3.3 View 邊界：驗證 CheckMacValue

來源：`ecpay_mock/gateway/views.py::_verify_check_mac_value()`（約第 313 行起）。商城送來的 CheckMacValue 應在進入 Service 前驗證；銀行端的另一段簽章由 Ecpay Mock 對 Bank Mock 的 Adapter 流程處理。

```python
def _verify_check_mac_value(
    data: dict,
) -> str:
    """
    【新增】

    Ecpay Mock View 的 Request Boundary MAC 驗證。

    正確流程：

        E_commerce
             ↓
        HTTP Request
             ↓
        View
             ↓
        CheckMacValue 驗證
             ↓
        ECPayService

    因此 CheckMacValue 驗證必須在 Service 之前完成。

    注意：

    這裡只驗證「E_commerce → Ecpay Mock」
    這一段的 CheckMacValue。

    Ecpay Mock → Bank Mock 的 CheckMacValue，
    由 ECPayMockAdapter 重新產生。
    """

    if not isinstance(
        data,
        dict,
    ):
        raise ValueError(
            "CheckMacValue 驗證資料格式錯誤"
        )

    incoming_check_mac = data.get(
        "CheckMacValue"
    )

    if not incoming_check_mac:
        raise ValueError(
            "缺少 CheckMacValue"
        )

    hash_key = getattr(
        settings,
        "ECPAY_HASH_KEY",
        "",
    )

    hash_iv = getattr(
        settings,
        "ECPAY_HASH_IV",
        "",
    )

    if not hash_key or not hash_iv:
        raise RuntimeError(
            "ECPAY_HASH_KEY / ECPAY_HASH_IV 未設定"
        )

    # --------------------------------------------------------
    # 【新增】
    #
    # 驗證 MAC 時：
    #
    #   CheckMacValue 本身不能再次參與計算。
    #
    # 因此只建立 copy，
```

### 3.4 `ECPayService.create_atm_payment()`：向銀行建立虛擬帳號

來源：`ecpay_mock/gateway/services/ecpay_service.py`（約第 1415 行起）。此方法是 ATM 建立的主要業務流程入口之一：驗證必要資料、呼叫 Gateway 取得銀行回應，再由金流端建立自己的交易資料。

```python
    def create_atm_payment(
        self,
        *,
        request_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        【修改】

        建立 ECPay Mock ATM Payment。

        ========================================================
        第一階段
        ========================================================

        接收：

            E_commerce
                ↓
            ecpay_gateway_checkout/

        ========================================================
        第二階段
        ========================================================

        呼叫：

            ECPayMockAdapter
                ↓
            Bank Mock

        ========================================================
        第三階段
        ========================================================

        Bank Mock 回傳：

            bank_code
            v_account
            expire_date

        ========================================================
        第四階段
        ========================================================

        ECPayService：

            產生 trade_no
            ↓
            建立 PaymentRequest
            ↓
            回傳 ATM 資訊
        """

        try:
            # ==================================================
            # 【新增】
            # 基本輸入驗證
            # ==================================================

            if not isinstance(
                request_data,
                dict,
            ):
                raise ValueError(
                    "request_data 必須是 dict"
                )

            merchant_trade_no = (
                request_data.get(
                    "merchant_trade_no"
                )
            )

            trade_amt = (
                request_data.get(
                    "trade_amt"
                )
            )

            item_name = (
                request_data.get(
```

### 3.5 Ecpay Mock 的 Gateway Interface

來源：`ecpay_mock/gateway/interface/ecpay_gateway.py`

```python
# ============================================================
# ECPay Mock
# gateway/interface/ecpay_gateway.py
# ============================================================

from abc import ABC, abstractmethod
from typing import Any, Dict


class ECPayGateway(ABC):
    """
    【修改】

    ECPay Mock Gateway Interface。

    ============================================================
    目前實際用途
    ============================================================

    在 Ecpay Mock 專案內：

        ECPayService
              ↓
        ECPayGateway
              ↓
        ECPayMockAdapter
              ↓ HTTPX
        Bank Mock

    因此這個 Interface 的實作，
    實際上負責 ECPay Mock → Bank Mock 的外部呼叫。

    ============================================================
    Gateway / Adapter 不負責
    ============================================================

    1. 不直接操作 Django ORM
    2. 不建立 PaymentRequest
    3. 不建立 PaymentNotification
    4. 不產生 ECPay trade_no
    5. 不產生 bank_code
    6. 不產生 v_account
    7. 不產生 expire_date
    8. 不負責商業流程
    9. 不由 View 直接呼叫 HTTPX

    ============================================================
    資料來源
    ============================================================

    Bank Mock 負責提供：

        bank_code
        v_account
        expire_date
        payment_status

    ECPayService 再根據結果建立自己的 trade_no。
    """

    @abstractmethod
    def create_atm_payment(
        self,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        【修改】

        請求 Bank Mock 建立 ATM 虛擬帳號。

        預期回傳：

            {
                "success": True,
                "merchant_trade_no": "...",
                "bank_code": "...",
                "v_account": "...",
                "expire_date": "...",
                "payment_status": "...",
                "response_data": {...},
            }

        注意：

        provider_transaction_id / trade_no
        不由 Adapter 產生。
        """

        raise NotImplementedError

    # 【新增】取消 ATM 虛擬帳號（ECPay Mock → Bank Mock）
    @abstractmethod
    def cancel_account(
        self,
```

### 3.6 銀行付款通知與商城通知

主要入口／方法：

- `gateway/views.py::payment_notify`（約第 657 行起）：接收 Bank Mock 通知。
- `gateway/services/ecpay_service.py::process_payment_notification`（約第 527 行起）：處理通知與狀態。
- `gateway/views.py::notify_shop`（約第 2103 行起）：View 中存在商城通知相關入口／輔助流程，需以完整實作確認其呼叫路徑。
- `gateway/adapters/store_payment_adapter.py`：商城端外部通知 Adapter。

注意：不要把 `gateway/services/payment_service.py` 與 `gateway/services/ecpay_service.py` 當成同一個 Service；ATM 建立與銀行通知的核心方法在 `ECPayService` 中。

## 4. Bank_site：銀行模擬端分層

### 4.1 主要檔案索引

| 層級 | 檔案 | 責任 |
|---|---|---|
| 專案 URL | `Bank_site/Bank_site/urls.py` | 將 `/notify/` 路由交給 `notify.urls`；首頁導向查詢與模擬頁 |
| App URL | `Bank_site/notify/urls.py` | 建立帳號、查詢帳號、模擬付款成功／失敗／逾期、取消帳號的路由 |
| View | `Bank_site/notify/views.py` | 接收使用者操作與 Ecpay Mock 建立帳號請求，回傳頁面／HTTP response |
| Service | `Bank_site/notify/services/bank_account_service.py` | ATM 帳號建立、查詢、付款成功／失敗／逾期／取消等業務流程 |
| Interface | `Bank_site/notify/interfaces/bank_account_gateway.py` | 定義銀行 Adapter 提供的操作契約 |
| Adapter | `Bank_site/notify/adapters/bank_account_adapter.py` | CheckMacValue 驗證、虛擬帳號資料操作，以及 HTTPX 通知 Ecpay Mock |
| Model | `Bank_site/notify/models.py` | `VirtualAccount` 等銀行模擬資料 |
| Template | `Bank_site` 專案 templates | 銀行帳號查詢與付款狀態模擬頁；以 View 的 `render()` 呼叫為準 |

### 4.2 Bank Mock 路由

來源：`Bank_site/notify/urls.py`

```python
from django.urls import path,include
from notify.views import (
    home,
    create_account,
    account_detail,
    simulate_paid,
    simulate_failed,
    simulate_expired,   # 【新增】模擬逾期未付款
    cancel_account,     # 【新增】取消 ATM 虛擬帳號（ECPay Mock 呼叫）
    db_query_tool,
    query_and_simulate,   # 新增:import 新的 view
#     ecpay_notify,
)

app_name = "notify"

urlpatterns = [
    path('', home, name='home'),
    path('create_account/', create_account, name='create_account'),
    path("account_detail/<str:merchant_trade_no>/",account_detail,name="account_detail"),
    path("simulate_paid/<str:merchant_trade_no>/",simulate_paid,name="simulate_paid"),
    path("simulate_failed/<str:merchant_trade_no>/",simulate_failed,name="simulate_failed"),
    path("simulate_expired/<str:merchant_trade_no>/",simulate_expired,name="simulate_expired"),  # 【新增】模擬逾期未付款
    path("cancel_account/<str:merchant_trade_no>/",cancel_account,name="cancel_account"),  # 【新增】取消 ATM 虛擬帳號
    path("admin-tools/db_query_tool/", db_query_tool, name="db_query_tool"),  # 新增
    path("admin-tools/query_and_simulate/", query_and_simulate, name="query_and_simulate"),  # 新增:查詢+模擬付款合併頁
#     path("notify/", ecpay_notify, name="ecpay_notify"),        # 綠界 server-to-server 回傳
]

```

### 4.3 `BankAccountService.simulate_paid()`：先通知下游，再更新銀行狀態

來源：`Bank_site/notify/services/bank_account_service.py`（約第 360 行起）。此方法的關鍵設計是：先通知 Ecpay Mock 處理付款結果，並檢查通知回應；下游成功後才繼續更新銀行端資料，以避免通知失敗卻先將銀行狀態標成已付款。

```python
    def simulate_paid(
        self,
        merchant_trade_no: str,
    ) -> dict:
        """
        模擬 ATM 付款成功。

        【修改】流程對調：

            先通知 ECPay Mock（含商店更新）
              ↓ 成功才
            寫 Bank DB status = paid
        """

        account = self.get_account(
            merchant_trade_no
        )

        # 【新增】已取消的帳號不可再模擬付款
        if account.status == "cancelled":
            raise ValueError(
                "此 ATM 帳號已取消，無法模擬付款"
            )

        # ====================================================
        # 【保留】
        # 防止重複付款
        # ====================================================

        if account.status == "paid":

            raise ValueError(
                "此 ATM 帳號已經付款完成"
            )

        # ====================================================
        # 【搬移】Bank → ECPay Mock 通知，從「寫 DB 之後」移到「之前」
        # payload 只讀 account，不需要先改狀態
        # ====================================================

        try:

            result = (
                self.gateway.notify_ecpay_mock(
                    account=account,
                    payment_status="paid",
                )
            )

        except Exception as ex:

            logger.exception(
                "Bank Mock → ECPay Mock "
                "付款成功 callback 失敗"
            )

            raise RuntimeError(
                "通知 ECPay Mock 付款成功失敗"
            ) from ex

        # ====================================================
        # 【新增】
        # adapter 失敗時回 {"status": False}，不會丟例外，
        # 這裡要主動檢查：失敗就不寫 Bank DB，並帶出原因
        # ====================================================

        if not result.get("status"):

            raise RuntimeError(
                "ECPay Mock 處理失敗，Bank 未更新："
                f"{result.get('response') or result.get('message')}"
            )

        # ====================================================
        # 【搬移】
        # 原本在通知之前的 transaction.atomic() 區塊，
        # 內容原封不動，搬到下游成功之後。
        # ====================================================

        try:

            with transaction.atomic():

                account = (
                    VirtualAccount.objects
                    .select_for_update()
                    .get(
                        merchant_trade_no=merchant_trade_no
                    )
```

### 4.4 `BankAccountAdapter`：HTTPX 與簽章責任

來源：`Bank_site/notify/adapters/bank_account_adapter.py`。此 Adapter 內部匯入 `httpx` 與 `generate_check_mac_value`，負責銀行端對外呼叫與 CheckMacValue 處理；這些協定細節不應由 View 直接執行。

```python
# ============================================================
# Bank Mock
# notify/adapters/bank_account_adapter.py
# ============================================================

import hmac
import logging
import random

import httpx

from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from util.ChkMacVal import (
    generate_check_mac_value,
)

from ..models import VirtualAccount

from ..interfaces.bank_account_gateway import (
    BankAccountGateway,
)


logger = logging.getLogger(__name__)


class BankAccountAdapter(BankAccountGateway):
    """
    【本次修改】

    Bank Mock ATM Adapter。

    Adapter 負責：

        1. 驗證 ECPay Mock → Bank Mock 的 CheckMacValue
        2. 產生 bank_code
        3. 產生 v_account
        4. 產生 expire_date
        5. 寫入 VirtualAccount
        6. 查詢 VirtualAccount
        7. 更新 VirtualAccount
        8. HTTPX 通知 ECPay Mock

    ============================================================
    Service 不負責
    ============================================================

        ❌ HTTPX
        ❌ CheckMacValue 計算
        ❌ CheckMacValue 驗證

    ============================================================
    最終架構
    ============================================================

        View
          ↓
        BankAccountService
          ↓
        BankAccountGateway
          ↓
        BankAccountAdapter
          ↓
        VirtualAccount / HTTPX / CheckMacValue
    """

    # ========================================================
    # 初始化
    # ========================================================

    def __init__(self):

        # ----------------------------------------------------
        # 【保留】
        # Bank Code
        # ----------------------------------------------------

        self.bank_code = getattr(
            settings,
            "BANK_MOCK_BANK_CODE",
            "013",
        )

        # ----------------------------------------------------
        # 【保留】
        # ATM 有效期限
        # ----------------------------------------------------

        self.expire_days = getattr(
            settings,
            "BANK_MOCK_EXPIRE_DAYS",
            3,
        )

        # ----------------------------------------------------
        # 【保留】
        # ECPay Mock callback URL
        # ----------------------------------------------------

```

### 4.5 其他 ATM 模擬狀態入口

`Bank_site/notify/services/bank_account_service.py` 內有下列方法：

- `create_account()`（約第 77 行）：建立虛擬帳號。
- `get_account()`（約第 313 行）：查詢虛擬帳號。
- `simulate_paid()`（約第 360 行）：模擬付款成功。
- `simulate_failed()`（約第 636 行）：模擬付款失敗。
- `cancel_account()`（約第 768 行）：取消 ATM 帳號。
- `simulate_expired()`（約第 817 行）：模擬逾期未付款。

相對應 View：`notify/views.py` 中的 `create_account()`、`account_detail()`、`simulate_paid()`、`simulate_failed()`、`simulate_expired()`、`cancel_account()`。

## 5. 狀態模擬與責任邊界

| 操作 | 使用者操作入口 | 業務 Service | 跨專案通知主要方向 |
|---|---|---|---|
| 建立 ATM 虛擬帳號 | E_commerce 結帳 | 商城 `OrderService` → Ecpay `ECPayService` → Bank `BankAccountService` | E_commerce → Ecpay_mock → Bank_site |
| 模擬付款成功 | Bank Mock 模擬頁 | `BankAccountService.simulate_paid()` | Bank_site → Ecpay_mock → E_commerce |
| 模擬付款失敗 | Bank Mock 模擬頁 | `BankAccountService.simulate_failed()` | Bank_site → Ecpay_mock，後續依通知處理更新商城狀態 |
| 模擬逾期 | Bank Mock 模擬頁 | `BankAccountService.simulate_expired()` | Bank_site → Ecpay_mock，後續依通知處理更新商城狀態 |
| 取消訂單／帳號 | 商城訂單操作或金流／銀行入口 | 商城 `PaymentService.cancel_order()`、Ecpay `ECPayService.cancel_order()`、Bank `BankAccountService.cancel_account()` | 通常由上游往下游同步取消；須確認每個入口的實際呼叫順序 |

## 6. 重要資料欄位與一致性檢查

建立 ATM 與付款通知時，請特別比對以下欄位是否在三個專案間一致：

- 商城訂單識別：`order_number`／`merchant_trade_no`。商城送出的商家交易編號通常以既有訂單編號為基礎，不要在下游隨意改成另一個值。
- 金流交易識別：Ecpay Mock 自己的 `trade_no` 或付款資料中的交易識別欄位，與商城訂單編號用途不同。
- 銀行帳號資料：`bank_code`、`v_account`、`expire_date`。
- 付款金額：`trade_amt`，三方應使用一致金額並避免浮點數誤差。
- 狀態：銀行、金流、商城可能使用不同狀態字串；應由各 Service 明確映射，不應假設三方狀態名稱完全相同。
- 簽章：每一段跨專案 HTTP 請求都應由該段的發送端簽署、接收端驗證；驗證時排除 `CheckMacValue` 本身。
- 通知失敗：需檢查 Adapter 回傳的成功旗標，不可只依「沒有丟出例外」就假定通知成功。
- 重複通知：callback 可能重送，付款成功應避免重複扣／釋放庫存或重複建立交易紀錄。
- 到期與取消：已取消或已付款帳號不可再次成功付款；逾期處理也應同步檢查商城訂單與付款狀態。

## 7. 維護時的分層規則

依這份 ZIP 中的介面與 Adapter 設計，維護時建議遵守以下邊界：

1. **View**：解析 HTTP request、驗證入口資料、呼叫 Service、組合 HTTP response；不要把跨專案 HTTPX 呼叫直接寫進 View。
2. **Service**：執行付款／訂單業務流程、狀態檢查、資料一致性控制。依目前專案設計，Service 可直接使用 Django ORM 的地方不要為了形式再強加 Repository。
3. **Interface / Gateway**：定義跨層呼叫契約，讓 Service 不依賴特定 Adapter 實作。
4. **Adapter**：負責 HTTPX、外部 URL、協定格式、CheckMacValue 等外部整合細節。
5. **Schema**：驗證輸入資料結構與欄位，不取代簽章驗證或業務狀態檢查。
6. **Model**：定義各專案自己的持久化資料；三個專案的資料庫記錄不會因為同名欄位而自動同步。
7. **Template**：負責呈現 ATM 資訊與模擬操作；狀態變更應透過 View → Service 流程執行。

## 8. ATM 頁面與程式快速查找表

| 想查的功能 | 檔案／方法 |
|---|---|
| 商城開始 ATM 結帳 | `E_commerce/commerce_shop/views.py::ecpay_checkout_redirect` |
| 商城組 ATM payload | `E_commerce/commerce_shop/services/order_service.py::prepare_ecpay_atm_checkout` |
| 商城呼叫金流介面 | `E_commerce/commerce_shop/interfaces/ecpay_gateway.py`、`adapters/ecpay_mock_adapter.py` |
| 金流接收 checkout | `ecpay_mock/gateway/views.py::ecpay_gateway_checkout` |
| 金流驗證商城簽章 | `ecpay_mock/gateway/views.py::_verify_check_mac_value` |
| 金流建立 ATM 付款 | `ecpay_mock/gateway/services/ecpay_service.py::create_atm_payment` |
| ATM 資訊頁 | `ecpay_mock/templates/atm_info.html`，並核對 `gateway/views.py::atm_info` 的 render |
| 銀行建立虛擬帳號 | `Bank_site/notify/views.py::create_account` → `BankAccountService.create_account` |
| 銀行模擬成功 | `Bank_site/notify/views.py::simulate_paid` → `BankAccountService.simulate_paid` |
| 金流接收銀行通知 | `ecpay_mock/gateway/views.py::payment_notify` → `ECPayService.process_payment_notification` |
| 商城接收 ATM 通知 | `E_commerce/commerce_shop/views.py::atm_payment_notify` → `PaymentService.handle_atm_callback` |
| 模擬逾期 | `Bank_site/notify/views.py::simulate_expired` → `BankAccountService.simulate_expired` |
| 取消訂單 | `E_commerce/commerce_shop/views.py::cancel_order`、`PaymentService.cancel_order`，並核對下游取消方法 |

## 9. 閱讀限制與驗證提醒

- 本文件是原始碼導覽，不等同於執行過端到端測試。
- ZIP 同時含有舊版註解路由、相容程式與目前啟用路由；應以 `urlpatterns` 中未被註解的路由為入口依據。
- `ecpay_mock` 是 ZIP 內實際目錄名稱；本文件依你的稱呼將其稱為 Ecpay_mock。
- ATM 模板可能有多個相似檔案（`atm_info.html`、`atm_payment.html`、`ecpay_atm_info.html`），應以 View 中實際 `render()` 的模板名稱判斷正在使用哪一個，不能只看檔名猜測。
- 部署時的 URL、HashKey／HashIV 與服務網址由各專案設定及環境變數決定；不要把開發環境的 `127.0.0.1` URL 直接當成部署設定。
