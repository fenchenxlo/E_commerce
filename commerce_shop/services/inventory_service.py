# commerce_shop/services/inventory_service.py

from django.db import transaction
from django.utils import timezone
from datetime import timedelta

from commerce_shop.models import (
    Product,
    Order,
    OrderItem,
    InventoryReservation,
)


class InventoryService:
    """
    【新增】

    庫存 Service。

    所有 Product.stock、
    Product.reserved_stock、
    InventoryReservation 的資料庫操作
    全部集中在這裡。

    View / API / OrderService
    不應直接修改 Product.stock。
    """

    RESERVATION_MINUTES = 30

    @staticmethod
    @transaction.atomic
    def reserve_order_inventory(order):
        """
        【新增】

        建立 Order 後，將 OrderItem 對應的商品庫存預留。

        規則：

            Product.stock -= quantity
            Product.reserved_stock += quantity

        同時建立：

            InventoryReservation
                status = reserved
        """

        order_items = (
            OrderItem.objects
            .select_related("product")
            .select_for_update()
            .filter(order=order)
        )

        for order_item in order_items:

            product = order_item.product
            quantity = order_item.quantity

            # --------------------------------------------------
            # 【新增】
            # 使用 select_for_update() 鎖住 Product。
            #
            # 避免兩個使用者同時 checkout：
            #
            # User A → stock = 5 → 買 4
            # User B → stock = 5 → 買 4
            #
            # 如果沒有 DB row lock，
            # 可能造成超賣。
            # --------------------------------------------------

            if product.stock < quantity:
                raise ValueError(
                    f"商品「{product.name}」庫存不足，"
                    f"目前可用庫存：{product.stock}，"
                    f"需要：{quantity}"
                )

            # --------------------------------------------------
            # 【新增】
            # Checkout 時先從可用庫存扣除。
            # --------------------------------------------------

            product.stock -= quantity

            # --------------------------------------------------
            # 【新增】
            # 同時增加 reserved_stock。
            # --------------------------------------------------

            product.reserved_stock += quantity

            product.save(
                update_fields=[
                    "stock",
                    "reserved_stock",
                ]
            )

            # --------------------------------------------------
            # 【新增】
            # 建立庫存預約紀錄。
            # --------------------------------------------------

            InventoryReservation.objects.create(
                order=order,
                product=product,
                quantity=quantity,
                status="reserved",
                expires_at=timezone.now()
                + timedelta(
                    minutes=InventoryService.RESERVATION_MINUTES
                ),
            )

    @staticmethod
    @transaction.atomic
    def commit_order_inventory(order):
        """
        【新增】

        付款成功。

        reserved_stock 減少。

        注意：

        stock 在 reserve 時已經扣掉，
        所以付款成功時不能再次扣 stock。

        只需要：

            reserved_stock -= quantity

        Reservation：

            reserved → committed
        """

        reservations = (
            InventoryReservation.objects
            .select_related("product")
            .select_for_update()
            .filter(
                order=order,
                status="reserved",
            )
        )

        for reservation in reservations:

            product = (
                Product.objects
                .select_for_update()
                .get(
                    product_id=reservation.product.product_id
                )
            )

            if product.reserved_stock < reservation.quantity:
                raise ValueError(
                    f"商品「{product.name}」reserved_stock "
                    f"資料異常。"
                )

            product.reserved_stock -= reservation.quantity

            product.save(
                update_fields=["reserved_stock"]
            )

            reservation.status = "committed"
            reservation.updated_at = timezone.now()
            reservation.save(
                update_fields=[
                    "status",
                    "updated_at",
                ]
            )

    @staticmethod
    @transaction.atomic
    def release_order_inventory(order):
        """
        【新增】

        付款失敗 / expired / cancelled。

        將預留庫存還回可用庫存：

            stock += quantity
            reserved_stock -= quantity

        Reservation：

            reserved → released
        """

        reservations = (
            InventoryReservation.objects
            .select_related("product")
            .select_for_update()
            .filter(
                order=order,
                status="reserved",
            )
        )

        for reservation in reservations:

            product = (
                Product.objects
                .select_for_update()
                .get(
                    product_id=reservation.product.product_id
                )
            )

            if product.reserved_stock < reservation.quantity:
                raise ValueError(
                    f"商品「{product.name}」"
                    f"reserved_stock 資料異常。"
                )

            product.stock += reservation.quantity
            product.reserved_stock -= reservation.quantity

            product.save(
                update_fields=[
                    "stock",
                    "reserved_stock",
                ]
            )

            reservation.status = "released"
            reservation.updated_at = timezone.now()

            reservation.save(
                update_fields=[
                    "status",
                    "updated_at",
                ]
            )