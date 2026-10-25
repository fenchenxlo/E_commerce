from decimal import Decimal
from typing import Literal

from ninja import Schema
from pydantic import Field


class SecondCheckoutSchema(Schema):
    """
    第二次 Checkout。

    enter_receiver_info.html
        ↓
    POST /api/checkout
        ↓
    更新 Order 收件資訊
        ↓
    ATM
        ↓
    呼叫 ECPay Mock
    """

    # ============================================================
    # 用來找到第一次建立的 Order
    # ============================================================

    order_number: str = Field(
        min_length=1,
        max_length=50
    )

    # ============================================================
    # 收件資訊
    # ============================================================

    receiver_name: str = Field(
        min_length=1,
        max_length=100
    )

    receiver_phone: str = Field(
        min_length=8,
        max_length=20
    )

    receiver_address: str = Field(
        min_length=1
    )

    # ============================================================
    # 訂單備註
    # ============================================================

    remark: str | None = None

    # ============================================================
    # 付款方式
    # ============================================================

    payment_method: Literal["ATM", "COD"]

    # ============================================================
    # 運費
    # ============================================================

    shipping_fee: Decimal = Field(
        default=Decimal("60"),
        ge=0
    )

    # ============================================================
    # 第二階段
    # ============================================================

    stage: int = 2