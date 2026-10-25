# commerce_shop/gateways/ecpay_gateway.py

from commerce_shop.adapters.ecpay_mock_adapter import (
    ECPayMockAdapter,
)


class ECPayGateway:
    """
    【新增】

    ECPay Gateway。

    PaymentService 不直接知道：

        ECPayMockAdapter

    PaymentService 只呼叫：

        ECPayGateway.create_payment()

    """

    def __init__(self):

        self.adapter = ECPayMockAdapter()

    def create_payment(
        self,
        payload: dict,
    ) -> dict:
        """
        【新增】

        Gateway 將付款請求交給 Adapter。
        """

        return self.adapter.create_payment(
            payload
        )