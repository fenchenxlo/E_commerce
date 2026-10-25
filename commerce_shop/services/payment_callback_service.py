# ============================================================
# commerce_shop/services/payment_callback_service.py
# ============================================================

import logging
from datetime import datetime

from django.db import transaction
from django.utils import timezone

from commerce_shop.models import (
    Order,
    Payment,
)

from commerce_shop.services.order_service import (
    OrderService,
)


logger = logging.getLogger(__name__)


class PaymentCallbackService:
    """
    【新增】

    專門處理：

        ECPay Mock
            ↓
        Store Callback
            ↓
        Payment
            ↓
        Order
            ↓
        InventoryReservation
    """

    @staticmethod
    def handle_atm_created(
        data,
    ):
        """
        ATM 虛擬帳號建立通知。

        注意：

        這裡不負責 HTTP request。
        View 只負責把 JSON 交進來。
        """

        try:

            merchant_trade_no = (
                data["merchant_trade_no"]
            )

            bank_code = data["bank_code"]

            v_account = data["v_account"]

            expire_date = data[
                "expire_date"
            ]

        except KeyError as exc:

            logger.exception(
                "[PaymentCallbackService] "
                "ATM callback 缺少欄位"
            )

            raise ValueError(
                f"ATM callback 缺少欄位：{exc}"
            ) from exc

        try:

            expire_datetime = (
                PaymentCallbackService
                .parse_datetime(
                    expire_date
                )
            )

            with transaction.atomic():

                order = (
                    Order.objects
                    .select_for_update()
                    .get(
                        order_number=(
                            merchant_trade_no
                        )
                    )
                )

                # ================================================
                # 【新增】
                # ATM Payment 每一次付款嘗試可以是一筆新的 Payment。
                #
                # 因為 New Model：
                #
                # 一個 Order
                #       ↓
                # 多個 Payment
                # ================================================

                payment = (
                    Payment.objects.create(
                        order=order,

                        provider="ecpay",

                        provider_transaction_id=(
                            data.get(
                                "provider_transaction_id"
                            )
                            or data.get(
                                "trade_no"
                            )
                        ),

                        payment_method="ATM",

                        amount=data.get(
                            "trade_amt",
                            order.total_amount,
                        ),

                        status="pending",

                        bank_code=bank_code,

                        v_account=v_account,

                        expire_date=(
                            expire_datetime
                        ),

                        response_data=data,
                    )
                )

                return payment

        except Order.DoesNotExist as exc:

            logger.exception(
                "[PaymentCallbackService] "
                "找不到 Order"
            )

            raise ValueError(
                "找不到訂單"
            ) from exc

        except Exception as exc:

            logger.exception(
                "[PaymentCallbackService] "
                "ATM Payment 建立失敗"
            )

            raise RuntimeError(
                "ATM Payment 建立失敗"
            ) from exc

    # ============================================================
    # 【新增】
    # Payment Result Callback
    # ============================================================

    @staticmethod
    def handle_payment_result(
        data,
    ):

        try:

            merchant_trade_no = (
                data["merchant_trade_no"]
            )

            result_status = (
                data["status"]
            )

        except KeyError as exc:

            logger.exception(
                "[PaymentCallbackService] "
                "Payment callback 欄位不足"
            )

            raise ValueError(
                f"缺少 callback 欄位：{exc}"
            ) from exc

        # ========================================================
        # 【新增】
        # 僅允許新的 Payment 狀態。
        # ========================================================

        if result_status not in (
            "success",
            "failed",
            "expired",
            "cancelled",
        ):

            raise ValueError(
                "不支援的付款結果"
            )

        try:

            with transaction.atomic():

                order = (
                    Order.objects
                    .select_for_update()
                    .get(
                        order_number=(
                            merchant_trade_no
                        )
                    )
                )

                provider_transaction_id = (
                    data.get(
                        "provider_transaction_id"
                    )
                    or data.get(
                        "trade_no"
                    )
                )

                payment = None

                if provider_transaction_id:

                    payment = (
                        Payment.objects
                        .select_for_update()
                        .filter(
                            provider=(
                                "ecpay"
                            ),
                            provider_transaction_id=(
                                provider_transaction_id
                            ),
                        )
                        .first()
                    )

                if not payment:

                    payment = (
                        Payment.objects
                        .select_for_update()
                        .filter(
                            order=order,
                            payment_method=(
                                data.get(
                                    "payment_method",
                                    "ATM",
                                )
                            ),
                        )
                        .order_by(
                            "-created_at"
                        )
                        .first()
                    )

                if not payment:

                    raise ValueError(
                        "找不到對應 Payment"
                    )

                # =================================================
                # SUCCESS
                # =================================================

                if result_status == "success":

                    payment.status = (
                        "success"
                    )

                    payment.paid_at = (
                        timezone.now()
                    )

                    payment.response_data = (
                        data
                    )

                    payment.save(
                        update_fields=[
                            "status",
                            "paid_at",
                            "response_data",
                            "updated_at",
                        ]
                    )

                    # ---------------------------------------------
                    # InventoryReservation
                    # ---------------------------------------------

                    OrderService().mark_order_paid(
                        order
                    )

                # =================================================
                # FAILED
                # =================================================

                elif result_status == "failed":

                    payment.status = (
                        "failed"
                    )

                    payment.response_data = (
                        data
                    )

                    payment.save(
                        update_fields=[
                            "status",
                            "response_data",
                            "updated_at",
                        ]
                    )

                # =================================================
                # EXPIRED
                # =================================================

                elif result_status == "expired":

                    payment.status = (
                        "expired"
                    )

                    payment.response_data = (
                        data
                    )

                    payment.save(
                        update_fields=[
                            "status",
                            "response_data",
                            "updated_at",
                        ]
                    )

                    OrderService().release_order_inventory(
                        order,
                        order_status="expired",
                    )

                # =================================================
                # CANCELLED
                # =================================================

                elif result_status == "cancelled":

                    payment.status = (
                        "cancelled"
                    )

                    payment.response_data = (
                        data
                    )

                    payment.save(
                        update_fields=[
                            "status",
                            "response_data",
                            "updated_at",
                        ]
                    )

                    OrderService().release_order_inventory(
                        order,
                        order_status="cancelled",
                    )

                return payment

        except Exception as exc:

            logger.exception(
                "[PaymentCallbackService] "
                "付款 Callback 處理失敗"
            )

            raise RuntimeError(
                "付款 Callback 處理失敗"
            ) from exc

    # ============================================================
    # 【新增】
    # 日期解析。
    # ============================================================

    @staticmethod
    def parse_datetime(
        value,
    ):

        if isinstance(
            value,
            datetime,
        ):

            result = value

        else:

            text = str(value).strip()

            try:

                result = (
                    datetime.fromisoformat(
                        text.replace(
                            "Z",
                            "+00:00",
                        )
                    )
                )

            except ValueError:

                result = (
                    datetime.strptime(
                        text,
                        "%Y-%m-%d %H:%M:%S",
                    )
                )

        if timezone.is_naive(result):

            result = timezone.make_aware(
                result
            )

        return result