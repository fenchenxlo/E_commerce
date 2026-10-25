# ============================================================
# commerce_shop/adapters/django_payment_repository.py
# ============================================================

import logging
from typing import Any, Dict, Optional


from commerce_shop.interfaces.payment_repository import (
    PaymentRepository,
)

from commerce_shop.models import (
    Order,
    Payment,
)


logger = logging.getLogger(__name__)


class DjangoPaymentRepository(PaymentRepository):
    """
    Django ORM implementation。

    【新增】

    只有這一本負責：

        Order.objects
        Payment.objects
        select_for_update()
        create()
        save()

    PaymentService 不直接碰 ORM。
    """

    # ============================================================
    # Order
    # ============================================================

    def get_order_for_update(
        self,
        merchant_trade_no: str,
    ):
        """
        【新增】
        取得並鎖定 Order。
        """

        if not merchant_trade_no:

            raise ValueError(
                "merchant_trade_no 不可為空"
            )

        try:

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

            return order

        except Exception as exc:

            logger.exception(
                "PaymentRepository 取得 Order 失敗"
            )

            raise RuntimeError(
                "取得訂單失敗"
            ) from exc

    # ============================================================
    # Payment by provider transaction id
    # ============================================================

    def get_payment_by_provider_transaction_id_for_update(
        self,
        provider_transaction_id: str,
    ):
        """
        【新增】

        第三方交易編號存在時，
        用它進行 callback idempotency。
        """

        if not provider_transaction_id:

            return None

        try:

            return (
                Payment.objects
                .select_for_update()
                .filter(
                    provider_transaction_id=(
                        provider_transaction_id
                    )
                )
                .order_by("-created_at")
                .first()
            )

        except Exception as exc:

            logger.exception(
                "依 provider_transaction_id "
                "查詢 Payment 失敗"
            )

            raise RuntimeError(
                "查詢 Payment 失敗"
            ) from exc

    # ============================================================
    # Payment by Order + v_account
    # ============================================================

    def get_payment_for_update(
        self,
        *,
        order,
        payment_method: str,
        v_account: str,
    ):
        """
        【新增】

        ATM callback idempotency：

            order
            payment_method
            v_account

        相同 ATM 虛擬帳號重複 callback
        不建立第二筆 Payment。
        """

        try:

            return (
                Payment.objects
                .select_for_update()
                .filter(
                    order=order,
                    payment_method=(
                        payment_method
                    ),
                    v_account=v_account,
                )
                .order_by("-created_at")
                .first()
            )

        except Exception as exc:

            logger.exception(
                "依 Order + v_account "
                "查詢 Payment 失敗"
            )

            raise RuntimeError(
                "查詢 Payment 失敗"
            ) from exc

    # ============================================================
    # Create Payment
    # ============================================================

    def create_payment(
        self,
        *,
        order,
        provider: str,
        payment_method: str,
        amount,
        status: str,
        bank_code: Optional[str],
        v_account: Optional[str],
        expire_date,
        provider_transaction_id: Optional[str],
        response_data: Optional[Dict[str, Any]],
    ):
        """
        【新增】
        ORM create 集中在 Repository。
        """

        try:

            return Payment.objects.create(
                order=order,
                provider=provider,
                payment_method=(
                    payment_method
                ),
                amount=amount,
                status=status,
                bank_code=bank_code,
                v_account=v_account,
                expire_date=expire_date,
                provider_transaction_id=(
                    provider_transaction_id
                ),
                response_data=response_data,
            )

        except Exception as exc:

            logger.exception(
                "建立 Payment 失敗"
            )

            raise RuntimeError(
                "建立 Payment 失敗"
            ) from exc

    # ============================================================
    # Save Payment
    # ============================================================

    def save_payment(
        self,
        payment,
        *,
        provider_transaction_id: Optional[str],
        status: str,
        bank_code: Optional[str],
        v_account: Optional[str],
        expire_date,
        response_data: Optional[Dict[str, Any]],
    ):
        """
        【新增】

        所有 Payment 更新集中在 Repository。
        """

        try:

            payment.provider_transaction_id = (
                provider_transaction_id
            )

            payment.status = status
            payment.bank_code = bank_code
            payment.v_account = v_account
            payment.expire_date = expire_date
            payment.response_data = response_data

            # ----------------------------------------------------
            # 【新增】
            #
            # updated_at 是 auto_now。
            # 使用 update_fields 時必須一起帶進去。
            # ----------------------------------------------------

            payment.save(
                update_fields=[
                    "provider_transaction_id",
                    "status",
                    "bank_code",
                    "v_account",
                    "expire_date",
                    "response_data",
                    "updated_at",
                ]
            )

            return payment

        except Exception as exc:

            logger.exception(
                "更新 Payment 失敗"
            )

            raise RuntimeError(
                "更新 Payment 失敗"
            ) from exc