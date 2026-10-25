# commerce_shop/interfaces/payment_gateway.py

from abc import ABC, abstractmethod


class PaymentGatewayInterface(ABC):
    """
    【新增】

    Payment Gateway Interface。

    Store Service 不知道：

        httpx
        URL
        ECPay Mock
        requests
        API endpoint

    Store Service 只知道：

        create_payment()

    未來如果換：

        ECPay
        Stripe
        NewebPay

    都可以實作這個 Interface。
    """

    @abstractmethod
    def create_payment(
        self,
        payload: dict,
    ) -> dict:
        """
        【新增】

        建立付款。

        Returns:
            dict
        """
        raise NotImplementedError