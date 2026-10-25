# ============================================================
# commerce_shop/services/order_query_service.py
# ============================================================

import logging

from django.db.models import Prefetch

from commerce_shop.models import (
    Order,
    Payment,
)


logger = logging.getLogger(__name__)


class OrderQueryService:
    """
    【新增】

    專門負責：

        Order 查詢
        Payment 查詢
        OrderItem 查詢

    View 不直接操作 ORM。
    """

    # 【新增】訂單頁「交易狀態」文字。
    # key 優先用 callback 原始 status（可分辨 COD 待出貨 / 配送中），
    # 找不到再用 Payment.status。
    PAYMENT_STATUS_TEXT = {
        # COD（ecpay_mock cod_gateway 模擬頁）
        "cod_confirmed": "待出貨，貨到超商時付現",
        "cod_created": "待出貨，貨到超商時付現",
        "cod_shipped": "配送中,待取貨付款",   # 與訂單標題 shipped(COD) 用語一致
        "cod_paid": "已取貨付款",
        "cod_failed": "取貨失敗未付款",
        "cod_expired": "逾期未付款",
        # ATM（Bank_site 模擬頁）
        "atm_created": "待付款",
        "paid": "已付款",
        "failed": "付款失敗",
        "expired": "逾期未付款",
        # Payment.status 備援
        "pending": "處理中",
        "success": "已付款",
        "cancelled": "已取消",
    }

    # 【新增】取得訂單最新一筆 Payment 的交易狀態文字；
    # 沒有 Payment（尚未選付款方式）回傳空字串。
    @classmethod
    def get_payment_status_text(
        cls,
        order,
    ):

        payments = getattr(order, "all_payments", [])

        if not payments:
            return ""

        payment = payments[0]

        data = (
            payment.response_data
            if isinstance(payment.response_data, dict)
            else {}
        )

        return (
            cls.PAYMENT_STATUS_TEXT.get(str(data.get("status")))
            or cls.PAYMENT_STATUS_TEXT.get(payment.status, "")
        )

    @staticmethod
    def get_user_orders(
        user,
    ):
        """
        取得目前登入使用者自己的訂單。

        注意：
        這裡沒有任何修改 DB 的操作。
        """

        try:

            orders = (
                Order.objects
                .filter(
                    user=user
                )
                .prefetch_related(
                    "items__product",
                    Prefetch(
                        "payments",
                        queryset=(
                            Payment.objects
                            .filter(
                                payment_method="ATM"
                            )
                            .order_by(
                                "-created_at"
                            )
                        ),
                        to_attr="atm_payments",
                    ),
                    # 【新增】所有付款方式的 Payment（新到舊），給訂單頁顯示「交易狀態」
                    Prefetch(
                        "payments",
                        queryset=(
                            Payment.objects
                            .order_by(
                                "-created_at"
                            )
                        ),
                        to_attr="all_payments",
                    ),
                )
                .order_by(
                    "-created_at"
                )
            )

            return list(orders)

        except Exception as exc:

            logger.exception(
                "[OrderQueryService.get_user_orders] "
                "讀取訂單失敗"
            )

            raise RuntimeError(
                "讀取訂單失敗"
            ) from exc