# commerce_shop/services/cart_service.py

from django.db import transaction

from commerce_shop.models import (
    Cart,
    CartItem,
)


class CartService:
    """
    【新增】

    Cart / CartItem 的資料庫操作集中在這裡。

    View 不直接：

        Cart.objects...
        CartItem.objects...
    """

    @staticmethod
    def get_or_create_cart(user):
        """
        【新增】
        取得使用者購物車。
        """

        cart, created = Cart.objects.get_or_create(
            user=user
        )

        return cart

    @staticmethod
    def get_cart_items(user):
        """
        【新增】

        取得購物車商品。
        """

        cart = CartService.get_or_create_cart(user)

        return (
            cart.items
            .select_related("product")
            .all()
        )

    @staticmethod
    @transaction.atomic
    def add_product(user, product, quantity=1):
        """
        【新增】

        加入購物車。

        注意：

        這裡只檢查目前 Product.stock。

        真正 checkout 時，
        InventoryService 還會再次 select_for_update()
        驗證庫存。

        這是必要的雙重防護。
        """

        cart = CartService.get_or_create_cart(user)

        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={
                "quantity": quantity,
                "price": product.price,
            },
        )

        if not created:

            new_quantity = (
                cart_item.quantity + quantity
            )

            if new_quantity > product.stock:
                raise ValueError(
                    f"庫存不足，最多只能購買 "
                    f"{product.stock} 個。"
                )

            cart_item.quantity = new_quantity

            cart_item.save(
                update_fields=["quantity"]
            )

        else:

            if product.stock < quantity:

                cart_item.delete()

                raise ValueError(
                    f"商品「{product.name}」庫存不足。"
                )

        return cart_item

    @staticmethod
    @transaction.atomic
    def update_quantity(
        user,
        product_id,
        quantity,
    ):
        """
        【新增】
        修改購物車數量。
        """

        cart = CartService.get_or_create_cart(user)

        cart_item = (
            CartItem.objects
            .select_related("product")
            .get(
                cart=cart,
                product_id=product_id,
            )
        )

        if quantity <= 0:
            cart_item.delete()
            return None

        if quantity > cart_item.product.stock:
            raise ValueError(
                f"庫存不足，目前可用庫存："
                f"{cart_item.product.stock}"
            )

        cart_item.quantity = quantity
        cart_item.save(
            update_fields=["quantity"]
        )

        return cart_item

    @staticmethod
    @transaction.atomic
    def remove_item(user, product_id):
        """
        【新增】
        移除購物車商品。
        """

        cart = CartService.get_or_create_cart(user)

        deleted, _ = (
            CartItem.objects
            .filter(
                cart=cart,
                product_id=product_id,
            )
            .delete()
        )

        return deleted

    @staticmethod
    @transaction.atomic
    def clear_cart(user):
        """
        【新增】

        Checkout 成功建立 Order 後，
        清空 CartItem。
        """

        cart = CartService.get_or_create_cart(user)

        cart.items.all().delete()

    @staticmethod
    def calculate_total(user):
        """
        【新增】

        計算目前購物車商品總額。
        """

        items = CartService.get_cart_items(user)

        return sum(
            item.price * item.quantity
            for item in items
        )