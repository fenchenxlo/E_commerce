# ============================================================
# commerce_shop/services/payment_service.py
# ============================================================

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Optional

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from commerce_shop.adapters.ecpay_mock_adapter import (
    ECPayMockAdapter,
)

from commerce_shop.models import (
    InventoryReservation,
    Order,
    Payment,
)


logger = logging.getLogger(__name__)


class PaymentService:
    """
    Payment Business Service。

    【修改】

    PaymentService 現在負責：

        1. 接收 API 傳入的既有 Order
        2. 呼叫 ECPayGateway
        3. 等 Bank Mock 建立完整 ATM 資訊
        4. 驗證：
            bank_code
            v_account
            expire_date
        5. ATM 資訊完整回到 E_commerce 後：
            Payment.objects.create(...)
        6. 處理之後的 ATM payment callback

    PaymentService：

        ✅ 可以直接使用 Django ORM

    不使用：

        ❌ PaymentRepository
        ❌ DjangoPaymentRepository
        ❌ httpx

    HTTPX 仍然只由：

        ECPayMockAdapter

    負責。
    """

    # ============================================================
    # 【保留】
    # ATM / Payment callback 狀態對應
    # ============================================================

    STATUS_MAP = {
        "pending": "pending",
        "atm_created": "pending",

        "paid": "success",
        "success": "success",
        "atm_paid": "success",

        "failed": "failed",
        "atm_failed": "failed",

        "expired": "expired",
        "atm_expired": "expired",

        "cancelled": "cancelled",
        "atm_cancelled": "cancelled",
    }
    
    # ============================================================
    # 【新增】COD callback 狀態對應
    # callback status → (Payment.status, Order.status)
    # ============================================================

    COD_STATUS_MAP = {
        "cod_confirmed": ("pending", "pending_payment"),
        "cod_created": ("pending", "pending_payment"),
        "cod_shipped": ("pending", "shipped"),
        "cod_paid": ("success", "paid"),
        "cod_failed": ("failed", "pending_payment"),
        "cod_expired": ("expired", "expired"),   # 【新增】逾期未付款：Payment/Order 皆 expired
    }    

    # ============================================================
    # 初始化
    # ============================================================

    def __init__(
        self,
        ecpay_gateway=None,
    ):
        """
        【修改】

        不再接收：

            repository

        只注入：

            ECPayGateway

        實際 production / demo 執行時：

            PaymentService
                    ↓
            ECPayGateway
                    ↓
            ECPayMockAdapter
                    ↓
                HTTPX
        """

        self.ecpay_gateway = (
            ecpay_gateway
            or ECPayMockAdapter()
        )

    # ============================================================
    # ATM Payment 建立
    # ============================================================

    def create_payment(
        self,
        *,
        user,
        order_number: str,
        payment_method: str,
    ) -> Dict[str, Any]:
        """
        建立 Payment。

        【修改】

        Payment 建立的真正時機：

            Store
                ↓
            ECPay Mock
                ↓
            Bank Mock
                ↓
            Bank Mock 真正建立 ATM
                ↓
            bank_code
            v_account
            expire_date
                ↓
            回到 E_commerce
                ↓
            才執行 Payment.objects.create()

        因此 Payment 不會出現：

            bank_code = NULL
            v_account = NULL
            expire_date = NULL

        的半成品 ATM Payment。

        """

        # ========================================================
        # 【新增】
        # 付款方式驗證
        # ========================================================

        if payment_method != "ATM":
            raise ValueError(
                "目前 PaymentService 只支援 ATM"
            )

        if not order_number:
            raise ValueError(
                "缺少 order_number"
            )

        # ========================================================
        # 【新增】
        # 取得使用者自己的 Order
        # ========================================================

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

        # ========================================================
        # 【新增】
        # Payment 使用的 Order 狀態驗證
        # ========================================================

        if order.status != "pending_payment":
            raise ValueError(
                f"目前訂單狀態為 {order.status}，"
                "無法建立 ATM Payment"
            )

        if order.payment_method != "ATM":
            raise ValueError(
                "Order 的 payment_method 不是 ATM"
            )

        # ========================================================
        # 【新增】
        # 商品名稱組合
        #
        # ECPay Mock 的 item_name 會顯示在 atm_info.html。
        # ========================================================

        item_names = ",".join(
            order.items.values_list(
                "name",
                flat=True,
            )
        )

        if not item_names:
            item_names = "購買商品"

        # ========================================================
        # 【新增】
        # Merchant Trade Date
        # ========================================================

        if order.created_at:

            merchant_trade_date = (
                timezone.localtime(
                    order.created_at
                ).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            )

        else:

            merchant_trade_date = (
                timezone.localtime().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            )

        # ========================================================
        # 【新增】
        # 建立送往 ECPay Mock 的 Gateway payload
        #
        # 注意：
        #
        # ATM 三個欄位：
        #
        # bank_code
        # v_account
        # expire_date
        #
        # 絕對不能由 Store 自己產生。
        # ========================================================

        merchant_id = getattr(
            settings,
            "ECPAY_MERCHANT_ID",
            "2000132",
        )

        gateway_payload = {
            "merchant_id": merchant_id,

            "merchant_trade_no": (
                order.order_number
            ),

            "merchant_trade_date": (
                merchant_trade_date
            ),

            "trade_amt": str(
                order.total_amount
            ),

            "trade_desc": (
                order.remark
                or "購買商品"
            ),

            "item_name": item_names,

            "payment_type": "aio",

            "choose_payment": "ATM",

            # 【新增】ecpay_mock 建立自己的 Order 紀錄所需欄位
            # （會一併簽進 CheckMacValue，ecpay_mock schema 已同步放行）
            "user_id": str(order.user_id),

            "receiver_name": (
                order.receiver_name
                or ""
            ),
        }

        # ========================================================
        # 【新增】
        # CheckMacValue
        #
        # Store → Ecpay Mock
        #
        # Store 必須先簽章。
        # ========================================================

        gateway_payload["CheckMacValue"] = (
            self._generate_check_mac_value(
                gateway_payload
            )
        )

        # ========================================================
        # 【新增】
        # 呼叫 ECPay Gateway
        #
        # PaymentService 不直接碰 HTTPX。
        # ========================================================

        try:

            atm_result = (
                self.ecpay_gateway
                .create_atm_payment(
                    gateway_payload
                )
            )

            logger.info(
                "ECPay Gateway 原始回應: %s",
                atm_result,
            )

        except ValueError:
            raise

        except RuntimeError:
            raise

        except Exception as exc:

            logger.exception(
                "ECPay ATM Gateway 呼叫失敗"
            )

            raise RuntimeError(
                "ATM 付款建立失敗"
            ) from exc

        # ========================================================
        # 【新增】
        # 驗證 Gateway response
        # ========================================================

        if not isinstance(
            atm_result,
            dict,
        ):
            raise RuntimeError(
                "ECPay Gateway 回傳格式錯誤"
            )

        gateway_success = (
            atm_result.get("success")
        )

        if gateway_success is None:

            gateway_status = (
                atm_result.get("status")
            )

            gateway_success = (
                gateway_status is True
                or gateway_status == "success"
            )

        if not gateway_success:

            raise RuntimeError(
                atm_result.get(
                    "message",
                    "ATM 付款建立失敗",
                )
            )

        # ========================================================
        # 【新增】
        # Ecpay Mock 最新回傳可能是：
        #
        # {
        #     "success": true,
        #     "payment": {
        #         ...
        #     },
        #     "atm_info_url": "..."
        # }
        #
        # 因此先取 payment。
        # ========================================================

        payment_data = (
            atm_result.get("payment")
        )

        if not isinstance(
            payment_data,
            dict,
        ):
            payment_data = atm_result

        # ========================================================
        # 【新增】
        # 驗證 merchant_trade_no
        # ========================================================

        response_merchant_trade_no = (
            payment_data.get(
                "merchant_trade_no"
            )
        )

        if not response_merchant_trade_no:
            raise RuntimeError(
                "ECPay Gateway 回應缺少 merchant_trade_no"
            )

        if (
            str(response_merchant_trade_no)
            != str(order.order_number)
        ):
            raise RuntimeError(
                "ECPay Gateway merchant_trade_no 不一致"
            )

        # ========================================================
        # 【新增】
        # 取得 Bank Mock 真正產生的 ATM 三個欄位
        # ========================================================

        bank_code = payment_data.get(
            "bank_code"
        )

        v_account = payment_data.get(
            "v_account"
        )

        expire_date = payment_data.get(
            "expire_date"
        )

        # ========================================================
        # 【新增】
        # ATM 三個欄位全部必須存在
        # ========================================================

        if not bank_code:
            raise RuntimeError(
                "Bank Mock 沒有回傳 bank_code"
            )

        if not v_account:
            raise RuntimeError(
                "Bank Mock 沒有回傳 v_account"
            )

        if not expire_date:
            raise RuntimeError(
                "Bank Mock 沒有回傳 expire_date"
            )

        # ========================================================
        # 【新增】
        # expire_date 統一轉成 aware datetime
        # ========================================================

        expire_datetime = (
            self._normalize_expire_date(
                expire_date
            )
        )

        if (
            expire_datetime
            <= timezone.now()
        ):
            raise RuntimeError(
                "ATM 付款期限已經過期"
            )

        # ========================================================
        # 【新增】
        # ECPay Mock 產生的交易編號
        #
        # 不使用舊 transaction_id。
        # ========================================================

        provider_transaction_id = (
            payment_data.get(
                "trade_no"
            )
            or atm_result.get(
                "trade_no"
            )
        )

        if not provider_transaction_id:
            raise RuntimeError(
                "ECPay Gateway 回應缺少 trade_no"
            )

        # ========================================================
        # 【新增】
        # atm_info_url
        #
        # Ecpay Mock 已經建立好 ATM 頁面，
        # Store 只保存 URL，不自己建立 ATM HTML。
        # ========================================================

        atm_info_url = (
            atm_result.get(
                "atm_info_url"
            )
        )

        # ========================================================
        # 【新增】
        # Payment 完整建立
        #
        # 這裡才真正寫入：
        #
        # bank_code
        # v_account
        # expire_date
        #
        # 三個 ATM 資訊。
        # ========================================================

        with transaction.atomic():

            # ----------------------------------------------------
            # 【新增】
            # 防止相同 ECPay trade_no 重複建立。
            # ----------------------------------------------------

            payment = (
                Payment.objects
                .filter(
                    provider="ecpay",
                    provider_transaction_id=(
                        provider_transaction_id
                    ),
                )
                .first()
            )

            # ----------------------------------------------------
            # 【修改】
            # 如果相同交易已存在，
            # 直接更新 ATM 資訊。
            # ----------------------------------------------------

            if payment is not None:

                if payment.order_id != order.id:
                    raise RuntimeError(
                        "ECPay trade_no 已經屬於其他訂單"
                    )

                payment.payment_method = (
                    "ATM"
                )

                payment.amount = (
                    order.total_amount
                )

                payment.status = (
                    "pending"
                )

                payment.bank_code = (
                    str(bank_code)
                )

                payment.v_account = (
                    str(v_account)
                )

                payment.expire_date = (
                    expire_datetime
                )

                payment.payment_url = (
                    atm_info_url or ""
                )

                payment.response_data = (
                    atm_result
                )

                payment.save(
                    update_fields=[
                        "payment_method",
                        "amount",
                        "status",
                        "bank_code",
                        "v_account",
                        "expire_date",
                        "payment_url",
                        "response_data",
                        "updated_at",
                    ]
                )

            else:

                # ------------------------------------------------
                # 【新增】
                # 第一次建立完整 Payment。
                # ------------------------------------------------

                payment = (
                    Payment.objects.create(
                        provider="ecpay",

                        order=order,

                        payment_method="ATM",

                        amount=(
                            order.total_amount
                        ),

                        status="pending",

                        provider_transaction_id=(
                            str(
                                provider_transaction_id
                            )
                        ),

                        payment_url=(
                            atm_info_url or ""
                        ),

                        bank_code=(
                            str(bank_code)
                        ),

                        v_account=(
                            str(v_account)
                        ),

                        expire_date=(
                            expire_datetime
                        ),

                        paid_at=None,

                        response_data=(
                            atm_result
                        ),
                    )
                )

        # ========================================================
        # 【新增】
        # 回傳給 API
        # ========================================================

        return {
            "payment_number": str(
                payment.payment_number
            ),

            "provider": (
                payment.provider
            ),

            "provider_transaction_id": (
                payment.provider_transaction_id
            ),

            "payment_method": (
                payment.payment_method
            ),

            "amount": str(
                payment.amount
            ),

            "status": (
                payment.status
            ),

            "bank_code": (
                payment.bank_code
            ),

            "v_account": (
                payment.v_account
            ),

            "expire_date": (
                payment.expire_date.isoformat()
                if payment.expire_date
                else None
            ),

            "payment_url": (
                payment.payment_url
            ),

            "atm_info_url": (
                payment.payment_url
            ),

            "response_data": (
                payment.response_data
            ),
        }

    # ============================================================
    # CheckMacValue
    # ============================================================

    def _generate_check_mac_value(
        self,
        payload: Dict[str, Any],
    ) -> str:
        """
        【新增】

        Store → Ecpay Mock：

        先移除原有 CheckMacValue，
        再重新計算。

        """

        from util.ChkMacVal import (
            generate_check_mac_value,
        )

        payload_for_mac = dict(payload)

        payload_for_mac.pop(
            "CheckMacValue",
            None,
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

        if not hash_key:
            raise RuntimeError(
                "未設定 ECPAY_HASH_KEY"
            )

        if not hash_iv:
            raise RuntimeError(
                "未設定 ECPAY_HASH_IV"
            )

        return generate_check_mac_value(
            payload_for_mac,
            hash_key,
            hash_iv,
        )

    # ============================================================
    # expire_date normalize
    # ============================================================

    def _normalize_expire_date(
        self,
        expire_date,
    ):
        """
        【新增】

        支援：

            datetime
            ISO datetime string
            一般 datetime string
        """

        if isinstance(
            expire_date,
            datetime,
        ):

            value = expire_date

        else:

            value = parse_datetime(
                str(expire_date)
            )

            if value is None:

                raise ValueError(
                    "expire_date 格式錯誤"
                )

        if timezone.is_naive(
            value
        ):
            value = timezone.make_aware(
                value,
                timezone.get_current_timezone(),
            )

        return value

    # ============================================================
    # ATM Payment Callback
    # ============================================================

    # ============================================================
    # 【新增】COD callback
    #
    # 超商取貨付款，ecpay_mock → Store。
    # 同一筆可來回切換（待出貨 / 已送達 / 已付款 / 失敗），
    # 庫存預留跟著 paid 進出，邏輯與 ATM 相同。
    # ============================================================

    def handle_cod_callback(
        self,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:

        if not isinstance(payload, dict):
            raise ValueError("callback payload 必須是 dict")

        merchant_trade_no = payload.get("merchant_trade_no")
        callback_status = str(payload.get("status") or "").lower()
        trade_amt = payload.get("trade_amt")
        provider_transaction_id = (
            payload.get("provider_transaction_id")
            or payload.get("trade_no")
        )

        if not merchant_trade_no:
            raise ValueError("callback 缺少 merchant_trade_no")

        if callback_status not in self.COD_STATUS_MAP:
            raise ValueError(f"不支援的 COD 狀態：{callback_status}")

        if trade_amt in (None, ""):
            raise ValueError("callback 缺少 trade_amt")

        if not provider_transaction_id:
            raise ValueError("callback 缺少 provider_transaction_id")

        try:
            callback_amount = Decimal(str(trade_amt))
        except Exception as exc:
            raise ValueError("callback trade_amt 格式錯誤") from exc

        payment_status, target_order_status = (
            self.COD_STATUS_MAP[callback_status]
        )

        with transaction.atomic():

            order = (
                Order.objects
                .select_for_update()
                .filter(order_number=merchant_trade_no)
                .first()
            )

            if not order:
                raise ValueError("找不到 callback 對應的 Order")

            if order.payment_method != "COD":
                raise ValueError("callback 對應的 Order 並非 COD")

            if callback_amount != order.total_amount:
                raise ValueError("callback 付款金額與訂單金額不一致")

            # 已取消 / 逾期 / 完成的訂單不再被改狀態
            # 【修改】逾期訂單例外：只放行帶 simulate="1" 的模擬頁通知（已簽進 CheckMacValue）
            if order.status not in (
                "pending_payment",
                "paid",
                "shipped",
            ) and not (
                order.status == "expired"
                and str(payload.get("simulate", "")) == "1"
            ):
                raise ValueError(
                    f"目前訂單狀態為 {order.status}，"
                    "無法更新 COD 狀態"
                )

            # ---------------- Payment ----------------
            payment = (
                Payment.objects
                .select_for_update()
                .filter(
                    provider="ecpay",
                    provider_transaction_id=str(provider_transaction_id),
                )
                .first()
            )

            payment_fields = {
                "payment_method": "COD",
                "amount": order.total_amount,
                "status": payment_status,
                "response_data": payload,
                "paid_at": (
                    timezone.now()
                    if payment_status == "success"
                    else None
                ),
            }

            if payment is None:
                payment = Payment.objects.create(
                    provider="ecpay",
                    order=order,
                    provider_transaction_id=str(provider_transaction_id),
                    payment_url="",
                    **payment_fields,
                )
            else:
                if payment.order_id != order.id:
                    raise ValueError("trade_no 已經屬於其他訂單")

                for field, value in payment_fields.items():
                    setattr(payment, field, value)

                payment.save(
                    update_fields=list(payment_fields.keys()) + ["updated_at"]
                )

            # ---------------- 庫存預留 ----------------
            # 【新增】逾期改回其他狀態：先把已釋放的庫存重新預留（不足則整筆 rollback）
            if order.status == "expired" and target_order_status != "expired":
                self._re_reserve_inventory(order)

            if target_order_status == "paid" and order.status != "paid":
                self._commit_inventory(order)
            elif order.status == "paid" and target_order_status != "paid":
                self._recommit_to_reserved(order)

            # 【新增】逾期：釋放庫存預留（reserved → released，stock 加回）
            # 若原本是 paid，上面已先還原成 reserved，這裡才釋放得到
            if target_order_status == "expired":
                self._release_inventory(order)

            # ---------------- Order ----------------
            order_update_fields = ["status", "updated_at"]
            order.status = target_order_status

            # 【修改】門市資訊改寫入 Payment（原本寫在 Order）
            # 【重點】Payment 在上方已建立/更新，這裡只補門市欄位再存一次
            if payload.get("cvs_store_name"):
                payment.cvs_store_name = str(payload["cvs_store_name"])
                payment.cvs_store_address = str(
                    payload.get("cvs_store_address", "")
                )
                payment.save(
                    update_fields=[
                        "cvs_store_name",
                        "cvs_store_address",
                        "updated_at",
                    ]
                )
                # 【刪除】order.cvs_store_name / order.cvs_store_address
                # order_update_fields += ["cvs_store_name", "cvs_store_address"]

            # 【刪除】不再使用 _allow_expired_change（改由 simulate 標記判斷）
            order.save(update_fields=order_update_fields)

        return {
            "success": True,
            "merchant_trade_no": order.order_number,
            "payment_number": str(payment.payment_number),
            "payment_status": payment.status,
            "order_status": order.status,
            "message": "COD 狀態更新成功。",
        }
        
    def handle_atm_callback(
        self,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        處理：

            Ecpay Mock
                ↓
            Store atm_payment_notify
                ↓
            PaymentService
                ↓
            建立 / 更新 Payment

        【修改】

        Payment 建立的真正時機：

            enter_receiver_info.html
                    ↓
            /api/checkout
                    ↓
            OrderService 更新 Order
                    ↓
            Ecpay Mock
                    ↓
            Bank Mock
                    ↓
            ATM 建立成功
                    ↓
            Ecpay Mock 回 Store
                    ↓
            PaymentService
                    ↓
            Payment.objects.create()

        因此 callback 第一次收到完整 ATM 資訊時，
        Store 才建立 Payment。

        如果 callback 重送：
            使用 provider_transaction_id
            找到既有 Payment 後更新，
            不重複建立 Payment。
        """

        # ========================================================
        # 【新增】
        # Payload 型別驗證
        # ========================================================

        if not isinstance(
            payload,
            dict,
        ):
            raise ValueError(
                "callback payload 必須是 dict"
            )

        # ========================================================
        # 【新增】
        # 基本欄位
        # ========================================================

        merchant_trade_no = (
            payload.get(
                "merchant_trade_no"
            )
        )

        bank_code = (
            payload.get(
                "bank_code"
            )
        )

        v_account = (
            payload.get(
                "v_account"
            )
        )

        expire_date = (
            payload.get(
                "expire_date"
            )
        )

        trade_amt = (
            payload.get(
                "trade_amt"
            )
        )

        callback_status = (
            payload.get(
                "payment_status"
            )
            or payload.get(
                "status"
            )
            or "atm_created"
        )

        # ========================================================
        # 【新增】
        # provider_transaction_id
        #
        # 優先使用 ECPay Mock 明確回傳的：
        #
        #     provider_transaction_id
        #
        # 舊格式則 fallback：
        #
        #     trade_no
        # ========================================================

        provider_transaction_id = (
            payload.get(
                "provider_transaction_id"
            )
            or payload.get(
                "trade_no"
            )
        )

        if not merchant_trade_no:
            raise ValueError(
                "callback 缺少 merchant_trade_no"
            )

        if not bank_code:
            raise ValueError(
                "callback 缺少 bank_code"
            )

        if not v_account:
            raise ValueError(
                "callback 缺少 v_account"
            )

        if not expire_date:
            raise ValueError(
                "callback 缺少 expire_date"
            )

        if trade_amt in (
            None,
            "",
        ):
            raise ValueError(
                "callback 缺少 trade_amt"
            )

        if not provider_transaction_id:
            raise ValueError(
                "callback 缺少 provider_transaction_id"
            )

        # ========================================================
        # 【新增】
        # ATM 建立階段的狀態
        #
        # atm_created → pending
        # ========================================================

        payment_status = (
            self.STATUS_MAP.get(
                str(
                    callback_status
                ).lower()
            )
        )

        if payment_status is None:
            raise ValueError(
                f"不支援的付款狀態：{callback_status}"
            )

        # ========================================================
        # 【新增】
        # 金額
        # ========================================================

        try:

            callback_amount = Decimal(
                str(trade_amt)
            )

        except (
            TypeError,
            ValueError,
        ) as exc:

            raise ValueError(
                "callback trade_amt 格式錯誤"
            ) from exc

        # ========================================================
        # 【新增】
        # expire_date
        # ========================================================

        expire_datetime = (
            self._normalize_expire_date(
                expire_date
            )
        )

        # ========================================================
        # 【新增】
        # DB Transaction
        # ========================================================

        with transaction.atomic():

            # ----------------------------------------------------
            # 【新增】
            # 取得 Order
            # ----------------------------------------------------

            order = (
                Order.objects
                .select_for_update()
                .filter(
                    order_number=(
                        merchant_trade_no
                    )
                )
                .first()
            )

            if not order:
                raise ValueError(
                    "找不到 callback 對應的 Order"
                )

            # ----------------------------------------------------
            # 【新增】
            # Payment Method 驗證
            # ----------------------------------------------------

            if order.payment_method != "ATM":
                raise ValueError(
                    "callback 對應的 Order 並非 ATM"
                )

            # 【新增】逾期訂單不可被 ATM 通知改狀態（只有 COD 模擬頁可改）
            if order.status == "expired" and str(payload.get("simulate", "")) != "1":
                raise ValueError(
                    "訂單已逾期，無法更新 ATM 付款狀態"
                )

            # 【新增】已取消訂單是終態：任何 ATM 通知（含模擬頁）都不可改狀態，
            # 否則已釋放庫存的訂單會被改成 paid（Bank / ecpay_mock 端已擋，這裡是最後一道防線）
            if order.status == "cancelled":
                raise ValueError(
                    "訂單已取消，無法更新 ATM 付款狀態"
                )

            # ----------------------------------------------------
            # 【新增】
            # 金額一致性驗證
            # ----------------------------------------------------

            if (
                callback_amount
                != order.total_amount
            ):
                raise ValueError(
                    "callback 付款金額與訂單金額不一致"
                )

            # ====================================================
            # 【新增】
            # 找目前這個 ECPay trade_no 對應的 Payment
            #
            # 這是 idempotent 的關鍵。
            # ====================================================

            payment = (
                Payment.objects
                .select_for_update()
                .filter(
                    provider="ecpay",
                    provider_transaction_id=(
                        str(
                            provider_transaction_id
                        )
                    ),
                )
                .first()
            )

            # ====================================================
            # 【新增】
            # 如果沒有 Payment：
            #
            # 這是第一次收到 ATM 建立結果。
            # 現在才建立 Payment。
            # ====================================================

            if payment is None:

                payment = (
                    Payment.objects.create(

                        provider="ecpay",

                        order=order,

                        payment_method="ATM",

                        amount=(
                            order.total_amount
                        ),

                        status=(
                            payment_status
                        ),

                        provider_transaction_id=(
                            str(
                                provider_transaction_id
                            )
                        ),

                        payment_url=(
                            payload.get(
                                "atm_info_url",
                                "",
                            )
                            or ""
                        ),

                        bank_code=(
                            str(
                                bank_code
                            )
                        ),

                        v_account=(
                            str(
                                v_account
                            )
                        ),

                        expire_date=(
                            expire_datetime
                        ),

                        paid_at=None,

                        response_data=(
                            payload
                        ),
                    )
                )

                logger.info(
                    "Store Payment 建立成功："
                    "merchant_trade_no=%s, "
                    "provider_transaction_id=%s",
                    merchant_trade_no,
                    provider_transaction_id,
                )

            # ====================================================
            # 【修改】
            # Payment 已存在：
            #
            # callback 重送時更新同一筆，
            # 不建立第二筆 Payment。
            # ====================================================

            else:

                if (
                    payment.order_id
                    != order.id
                ):
                    raise ValueError(
                        "ECPay trade_no 已經屬於其他訂單"
                    )

                payment.payment_method = (
                    "ATM"
                )

                payment.amount = (
                    order.total_amount
                )

                payment.status = (
                    payment_status
                )

                payment.bank_code = (
                    str(
                        bank_code
                    )
                )

                payment.v_account = (
                    str(
                        v_account
                    )
                )

                payment.expire_date = (
                    expire_datetime
                )

                payment.payment_url = (
                    payload.get(
                        "atm_info_url",
                        payment.payment_url,
                    )
                    or payment.payment_url
                    or ""
                )

                payment.response_data = (
                    payload
                )

                # ------------------------------------------------
                # 【新增】
                # 只有真正 paid 才寫 paid_at。
                # ATM 建立階段為 pending。
                # ------------------------------------------------

                if (
                    payment_status == "success"
                ):

                    payment.paid_at = (
                        timezone.now()
                    )

                # ------------------------------------------------
                # 【新增】
                # 付款失敗（例如已付款後又模擬「未收到款項」）：
                # 清掉先前寫入的付款時間，避免 failed 卻還有 paid_at。
                # ------------------------------------------------

                elif (
                    # 【修改】逾期同失敗：清掉 paid_at
                    payment_status in ("failed", "expired")
                ):

                    payment.paid_at = None
                    
                payment.save(
                    update_fields=[
                        "payment_method",
                        "amount",
                        "status",
                        "bank_code",
                        "v_account",
                        "expire_date",
                        "payment_url",
                        "response_data",
                        "paid_at",
                        "updated_at",
                    ]
                )

                logger.info(
                    "Store Payment 已存在，更新既有 Payment："
                    "merchant_trade_no=%s, "
                    "provider_transaction_id=%s",
                    merchant_trade_no,
                    provider_transaction_id,
                )

            # ====================================================
            # 【新增】
            # ATM 建立完成：
            #
            # Order 仍然保持：
            #
            # pending_payment
            #
            # 不要現在就改成 paid。
            # ====================================================

            if payment_status == "success":

                # 【新增】只在 Order 還不是 paid 時才處理庫存，避免重送重複扣
                # 【新增】逾期訂單改成已付款：逾期時庫存已釋放，要先重新預留再 commit
                if order.status == "expired":
                    self._re_reserve_inventory(order)

                if order.status != "paid":
                    self._commit_inventory(order)
                    
                # 【修改】這行原本被誤貼成「order.status = "paid" and order.status in (...)」，會把 Order.status 寫成 True/False；還原為單純寫入 paid
                order.status = "paid"

                order.save(
                    update_fields=[
                        "status",
                        "updated_at",
                    ]
                )
            # ====================================================
            # 【新增】ATM 逾期未付款（callback status = expired）
            #
            # 【重點】Order / Payment 寫入點：
            #   Payment.status = "expired"        （上方既有流程已寫入）
            #   Order.status   = "expired"        （本區塊寫入）
            #   庫存：reserved → released，stock 加回
            #
            # 已付款(paid)的訂單先把庫存從 committed 退回 reserved，
            # 再一起釋放（與 COD cod_expired 的處理一致）。
            # 已出貨(shipped)的訂單不可逾期。
            # ====================================================
            elif payment_status == "expired":

                if order.status == "shipped":
                    raise ValueError(
                        "訂單已出貨，無法改為逾期未付款"
                    )

                if order.status == "paid":
                    self._recommit_to_reserved(order)

                self._release_inventory(order)

                order.status = "expired"
                order.save(
                    update_fields=[
                        "status",
                        "updated_at",
                    ]
                )


            # ====================================================
            # 【新增】
            # 付款失敗（未收到款項）：
            #
            # Order.status 沒有 failed，
            # 因此改回 pending_payment（等待付款）。
            #
            # 只降級 paid；processing / shipped / completed /
            # cancelled / expired 不動，避免誤改已進入後續流程的訂單。
            # ====================================================

            elif (
                payment_status == "failed"
                and order.status in ("paid", "expired")   # 【修改】逾期也可被模擬頁改回「未付款」
            ):

                # 【修改】paid → 把 committed 退回 reserved；expired → 庫存已釋放，重新預留
                if order.status == "expired":
                    self._re_reserve_inventory(order)
                else:
                    self._recommit_to_reserved(order)

                # 【新增】這行在你的版本裡被漏掉了：沒有它 Order 會一直停在 expired
                order.status = "pending_payment"

                order.save(
                    update_fields=[
                        "status",
                        "updated_at",
                    ]
                )
                
        # ========================================================
        # 【新增】
        # 回傳 Store ATM Payment 結果
        # ========================================================

        return {
            "success": True,

            "merchant_trade_no": (
                order.order_number
            ),

            "payment_number": str(
                payment.payment_number
            ),

            "provider_transaction_id": (
                payment.provider_transaction_id
            ),

            "payment_status": (
                payment.status
            ),

            "order_status": (
                order.status
            ),

            "bank_code": (
                payment.bank_code
            ),

            "v_account": (
                payment.v_account
            ),

            "expire_date": (
                payment.expire_date.isoformat()
                if payment.expire_date
                else None
            ),

            "atm_info_url": (
                payment.payment_url
            ),

            "message": (
                "ATM 付款資訊建立成功，"
                "Store Payment 已建立。"
            ),
        }
        
    # ============================================================
    # 【新增】
    # 付款成功：庫存預留 reserved → committed
    #
    # stock 不變（結帳時已扣），reserved_stock 扣回。
    # 已經是 committed 的不重複處理（callback 重送也安全）。
    # ============================================================

    def _commit_inventory(
        self,
        order: Order,
    ) -> None:

        reservations = (
            InventoryReservation.objects
            .select_for_update()
            .select_related("product")
            .filter(
                order=order,
                status="reserved",
            )
        )

        for reservation in reservations:

            product = reservation.product

            product.reserved_stock = max(
                product.reserved_stock
                - reservation.quantity,
                0,
            )

            product.save(
                update_fields=[
                    "reserved_stock",
                ]
            )

            reservation.status = "committed"

            reservation.save(
                update_fields=[
                    "status",
                    "updated_at",
                ]
            )

    # ============================================================
    # 【新增】
    # 已付款又被模擬「未收到款項」：
    # 庫存預留 committed → reserved（還原）
    #
    # 只還原 committed 的，其他狀態（例如 released）不動。
    # ============================================================

    def _recommit_to_reserved(
        self,
        order: Order,
    ) -> None:

        reservations = (
            InventoryReservation.objects
            .select_for_update()
            .select_related("product")
            .filter(
                order=order,
                status="committed",
            )
        )

        for reservation in reservations:

            product = reservation.product

            product.reserved_stock += (
                reservation.quantity
            )

            product.save(
                update_fields=[
                    "reserved_stock",
                ]
            )

            reservation.status = "reserved"

            reservation.save(
                update_fields=[
                    "status",
                    "updated_at",
                ]
            )

    # ============================================================
    # 【新增】取消訂單：E_commerce → ECPay Mock → Bank Mock
    # 順序：先通知下游成功，才寫 E_commerce DB 與釋放庫存
    # ============================================================

    def cancel_order(
        self,
        order: Order,
    ) -> None:

        # 【新增】只有待付款 / 付款失敗的訂單可取消
        if order.status not in ("pending_payment", "failed"):
            raise ValueError(
                "只有待付款或付款失敗的訂單可以取消"
            )

        # 【修改】COD 已支援取消（原本在此擋掉）。
        # COD 的 Order.status 對應：待出貨 / 取貨失敗 = pending_payment、配送中 = shipped、
        # 已取貨付款 = paid、逾期 = expired，所以上面的狀態判斷已排除不可取消的 COD 訂單；
        # ecpay_mock 端會再依 COD 狀態做最後把關。

        # 【新增】有 ATM 交易才需要通知 ecpay_mock → Bank Mock
        atm_payment = (
            order.payments
            .filter(
                payment_method="ATM",
                status__in=["pending", "failed"],
            )
            .first()
        )

        # 【修改】COD 一律通知 ecpay_mock（由其依 COD 狀態判斷能否取消）；
        # ATM 有交易才通知。下游失敗會拋例外，本地不寫入
        if order.payment_method == "COD":
            self.ecpay_gateway.cancel_payment(
                order.order_number,
                "COD",
            )
        elif atm_payment is not None:
            self.ecpay_gateway.cancel_payment(
                order.order_number,
                "ATM",
            )

        with transaction.atomic():

            # 【新增】釋放庫存：reserved → released
            self._release_inventory(order)

            order.status = "cancelled"
            order.save(
                update_fields=["status", "updated_at"]
            )

            # 【新增】交易狀態同步為已取消（訂單頁「交易狀態」）
            latest_payment = (
                order.payments
                .order_by("-created_at")
                .first()
            )

            if latest_payment is not None:
                latest_payment.status = "cancelled"
                latest_payment.save(
                    update_fields=["status", "updated_at"]
                )

    # ============================================================
    # 【新增】刪除「已取消」訂單前，通知 ecpay_mock（→ Bank）刪除對應紀錄
    # 順序：下游（Bank → ecpay_mock）先刪成功，呼叫端才刪商店自己的訂單；失敗拋例外、商店不刪。
    # 沒有 Payment（從未建立 ATM 帳號 / COD 單）的訂單，下游沒有紀錄，直接略過
    # ============================================================
    def delete_downstream_records(
        self,
        order: Order,
    ) -> None:

        if order.status != "cancelled":
            raise ValueError("訂單尚未取消，無法刪除付款紀錄")

        if not order.payments.exists():
            return

        self.ecpay_gateway.cancel_payment(
            order.order_number,
            "COD" if order.payment_method == "COD" else "ATM",
            delete_record=True,
        )

    # ============================================================
    # 【新增】
    # 釋放庫存預約
    # ============================================================

    def _release_inventory(
        self,
        order: Order,
    ) -> None:
        """
        付款失敗、取消或過期時：

            Product.stock
                ↑ quantity

            Product.reserved_stock
                ↓ quantity

            InventoryReservation
                reserved → released
        """

        reservations = (
            InventoryReservation.objects
            .select_related("product")
            .filter(
                order=order,
                status="reserved",
            )
        )

        for reservation in reservations:

            product = (
                reservation.product
            )

            product.stock += (
                reservation.quantity
            )

            product.reserved_stock = max(
                product.reserved_stock
                - reservation.quantity,
                0,
            )

            product.save(
                update_fields=[
                    "stock",
                    "reserved_stock",
                ]
            )

            reservation.status = (
                "released"
            )

            reservation.save(
                update_fields=[
                    "status",
                ]
            )

    # ============================================================
    # 【新增】
    # 逾期訂單被模擬頁改回其他狀態：released → reserved（stock 扣回）
    # ============================================================

    def _re_reserve_inventory(
        self,
        order: Order,
    ) -> None:

        reservations = (
            InventoryReservation.objects
            .select_for_update()
            .select_related("product")
            .filter(
                order=order,
                status="released",
            )
        )

        for reservation in reservations:

            product = reservation.product

            # 庫存不足就不還原（ValueError → 整個 transaction rollback）
            if product.stock < reservation.quantity:
                raise ValueError(
                    f"商品「{product.name}」庫存不足，無法還原逾期訂單"
                )

            product.stock -= reservation.quantity
            product.reserved_stock += reservation.quantity
            product.save(update_fields=["stock", "reserved_stock"])

            reservation.status = "reserved"
            reservation.save(update_fields=["status", "updated_at"])