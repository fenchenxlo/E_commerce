# ============================================================
# commerce_shop/interfaces/order_repository.py
# ============================================================

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class OrderRepository(ABC):
    """
    Order Repository Interface。

    【新增】

    Repository 的責任：

        專門處理資料庫存取。

    OrderService 不可以直接：

        Order.objects
        Product.objects
        Cart.objects
        OrderItem.objects
        InventoryReservation.objects

    OrderService 只能透過：

        OrderRepository

    取得或修改資料。

    ============================================================
    架構
    ============================================================

        OrderService
              │
              ▼
        OrderRepository
              │
              ▼
        DjangoOrderRepository
              │
              ▼
        Django ORM
              │
              ▼
        Database
    """

    # ========================================================
    # 第一階段：Cart
    # ========================================================

    @abstractmethod
    def get_cart_for_update(
        self,
        user,
    ):
        """
        取得指定 User 的 Cart。

        必須使用 select_for_update。
        """

        raise NotImplementedError

    @abstractmethod
    def get_cart_items_for_update(
        self,
        cart,
    ):
        """
        取得 CartItem。

        必須：

            select_related("product")
            select_for_update()
        """

        raise NotImplementedError

    @abstractmethod
    def clear_cart_items(
        self,
        cart,
    ) -> None:
        """
        清空 CartItem。
        """

        raise NotImplementedError

    # ========================================================
    # 第一階段：Order
    # ========================================================

    @abstractmethod
    def create_order(
        self,
        *,
        user,
        shipping_fee,
        total_amount,
        status,
        payment_method,
    ):
        """
        建立 Order。
        """

        raise NotImplementedError

    @abstractmethod
    def create_order_item(
        self,
        *,
        order,
        product,
        name,
        quantity,
        price,
    ):
        """
        建立 OrderItem。
        """

        raise NotImplementedError

    # ========================================================
    # 第一階段：Product
    # ========================================================

    @abstractmethod
    def save_product_stock(
        self,
        product,
        *,
        stock,
        reserved_stock,
    ) -> None:
        """
        更新 Product：

            stock
            reserved_stock
        """

        raise NotImplementedError

    # ========================================================
    # 第一階段：InventoryReservation
    # ========================================================

    @abstractmethod
    def create_inventory_reservation(
        self,
        *,
        order,
        product,
        quantity,
        status,
    ):
        """
        建立 InventoryReservation。
        """

        raise NotImplementedError

    # ========================================================
    # 第二階段：取得 Order
    # ========================================================

    @abstractmethod
    def get_order_for_update(
        self,
        *,
        user,
        order_number,
    ):
        """
        取得指定 User 的 Order。

        必須：

            select_for_update()
        """

        raise NotImplementedError

    @abstractmethod
    def save_order_checkout_data(
        self,
        order,
        *,
        receiver_name,
        receiver_phone,
        receiver_address,
        payment_method,
        remark,
    ) -> None:
        """
        儲存第二階段收件資料。
        """

        raise NotImplementedError

    # ========================================================
    # Payment Callback
    # ========================================================

    @abstractmethod
    def get_order_by_pk_for_update(
        self,
        *,
        order_pk,
    ):
        """
        依 PK 取得鎖定中的 Order。
        """

        raise NotImplementedError

    @abstractmethod
    def get_reservations_for_update(
        self,
        order,
    ):
        """
        取得 Order 的 InventoryReservation。

        必須：

            select_related("product")
            select_for_update()
        """

        raise NotImplementedError

    @abstractmethod
    def save_reservation(
        self,
        reservation,
        *,
        status,
    ) -> None:
        """
        更新 Reservation 狀態。
        """

        raise NotImplementedError

    @abstractmethod
    def save_product_reserved_stock(
        self,
        product,
        *,
        reserved_stock,
    ) -> None:
        """
        更新 Product.reserved_stock。
        """

        raise NotImplementedError

    @abstractmethod
    def save_product_inventory(
        self,
        product,
        *,
        stock,
        reserved_stock,
    ) -> None:
        """
        更新：

            Product.stock
            Product.reserved_stock
        """

        raise NotImplementedError

    @abstractmethod
    def save_order_status(
        self,
        order,
        *,
        status,
    ) -> None:
        """
        更新 Order.status。
        """

        raise NotImplementedError