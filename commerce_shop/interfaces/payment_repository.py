# ============================================================
# commerce_shop/interfaces/payment_repository.py
# ============================================================

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class PaymentRepository(ABC):
    """
    Payment Repository Interface。

    【新增】

    PaymentService 不直接操作 Django ORM。

    Service：

        PaymentService
              ↓
        PaymentRepository
              ↓
        DjangoPaymentRepository
              ↓
        Django ORM

    """

    # ============================================================
    # Order
    # ============================================================

    @abstractmethod
    def get_order_for_update(
        self,
        merchant_trade_no: str,
    ):
        """
        【新增】

        依 merchant_trade_no 取得並鎖定 Order。
        """

        raise NotImplementedError

    # ============================================================
    # Payment
    # ============================================================

    @abstractmethod
    def get_payment_by_provider_transaction_id_for_update(
        self,
        provider_transaction_id: str,
    ):
        """
        【新增】

        如果 ECPay Mock 有提供第三方交易編號，
        優先用它做 callback idempotency。
        """

        raise NotImplementedError

    @abstractmethod
    def get_payment_for_update(
        self,
        *,
        order,
        payment_method: str,
        v_account: str,
    ):
        """
        【新增】

        依：

            Order
            payment_method
            v_account

        找現有 Payment。

        這可以避免 Bank → ECPay → Store
        callback 重送時建立重複 Payment。

        如果未來同一 Order 產生不同 v_account，
        就可以建立新的 Payment。
        """

        raise NotImplementedError

    @abstractmethod
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

        建立新的 Payment。
        """

        raise NotImplementedError

    @abstractmethod
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

        更新 Payment。
        """

        raise NotImplementedError