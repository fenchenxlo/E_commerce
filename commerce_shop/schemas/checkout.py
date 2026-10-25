# ============================================================
# commerce_shop/schemas/checkout.py
# ============================================================
#
# CheckoutSchema
#
# 【修改】
#
# 這個 Schema 是 Store 前端：
#
#     enter_receiver_info.html
#             ↓
#         POST /api/checkout
#
# 所使用的資料格式。
#
# ------------------------------------------------------------
#
# 這裡只放「Checkout 第二階段真正需要的資料」。
#
# 不放：
#
#     ❌ Order.total_amount
#     ❌ Product.price
#     ❌ OrderItem subtotal
#     ❌ ECPay trade_no
#     ❌ ECPay CheckMacValue
#     ❌ HashKey
#     ❌ HashIV
#     ❌ ATM bank_code
#     ❌ ATM v_account
#     ❌ ATM expire_date
#
# 上述資料都由後端 Service / Gateway / Adapter 決定。
#
# ============================================================


from decimal import Decimal


# ============================================================
# Pydantic
# ============================================================

from pydantic import (
    ConfigDict,
    Field,
)


# ============================================================
# Django Ninja Schema
# ============================================================

from ninja import Schema


# ============================================================
# CheckoutSchema
# ============================================================

class CheckoutSchema(Schema):

    # ========================================================
    # 【新增】
    #
    # Pydantic v2 設定：
    #
    # extra="forbid"
    #
    # 如果前端偷偷多送：
    #
    #     total_amount
    #     trade_no
    #     bank_code
    #     v_account
    #
    # Schema 直接拒絕。
    #
    # ========================================================

    model_config = ConfigDict(
        extra="forbid"
    )


    # ========================================================
    # 【新增】
    #
    # Store Order Number
    #
    # 來源：
    #
    # purchased_products.html
    #         ↓
    # /enter_receiver_info/<order_number>/
    #         ↓
    # enter_receiver_info.html
    #         ↓
    # POST /api/checkout
    #
    # ========================================================

    order_number: str = Field(
        min_length=1,
        max_length=50,
    )


    # ========================================================
    # 收件人姓名
    # ========================================================

    receiver_name: str = Field(
        min_length=1,
        max_length=100,
        null=True,
        blank=True
    )


    # ========================================================
    # 收件人手機
    # ========================================================

    receiver_phone: str = Field(
        min_length=8,
        max_length=20,
        null=True,
        blank=True
    )


    # ========================================================
    # 收件地址
    # ========================================================

    receiver_address: str = Field(
        min_length=1,
        max_length=500,
        null=True,
        blank=True
    )


    # ========================================================
    # 付款方式
    # ========================================================
    #
    # 目前：
    #
    #     ATM
    #
    # 已保留：
    #
    #     COD
    #
    # 後面實作 COD 時再接。
    #
    # ========================================================

    payment_method: str = Field(
        min_length=3,
        max_length=3,
    )


    # ========================================================
    # 訂單備註
    # ========================================================

    remark: str = Field(
        default="",
        max_length=500,
        null=True,
        blank=True
    )


    # ========================================================
    # 【修改】
    #
    # shipping_fee 保留這個欄位，
    # 但第二階段不相信前端提供的金額。
    #
    # OrderService 目前會保留第一階段已計算好的
    # Order.total_amount。
    #
    # 因此：
    #
    #     shipping_fee
    #
    # 目前只是保留 Schema 相容性，
    # 不作為付款金額來源。
    #
    # ========================================================

    shipping_fee: Decimal = Field(
        default=Decimal("0.00"),
        ge=Decimal("0.00"),
    )