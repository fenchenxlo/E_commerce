from ninja import Schema


class FirstCheckoutSchema(Schema):
    """
    第一次 Checkout。

    目的：
    cart.html
        ↓
    POST /api/checkout
        ↓
    建立 Order

    第一次不需要：
    - receiver_name
    - receiver_phone
    - receiver_address
    - payment_method

    因為這些資料會在第二階段 enter_receiver_info.html 填寫。
    """

    stage: int = 1