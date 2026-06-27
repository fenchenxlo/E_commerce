from django.shortcuts import render, redirect, get_object_or_404  # 匯入 Django 的工具函式：render 用來渲染模板，redirect 用來重新導向，get_object_or_404 用來安全取得資料
from django.contrib.auth.decorators import login_required  # 匯入裝飾器，限制某些 view 必須登入才能使用
from .models import Product, Cart, CartItem, Order, OrderItem  # 匯入本 app 的模型：商品、購物車、購物車項目
from django.contrib import messages  # 匯入 Django 的訊息框架，用來顯示提示訊息
from django.db import transaction

def home(request):
    # 使用 Product.objects（ActiveProductManager在modols複寫了預設的get_queryset），只會回傳 is_deleted=False 的商品
    products = Product.objects.all()  
    # 將商品資料傳入 home.html 模板，並以字典形式提供給模板使用
    return render(request, 'home.html', {'products': products})

@login_required
def product_list(request):
    # 顯示登入會員自己擁有的商品，並過濾掉下架商品
    products = Product.objects.filter(owner=request.user, is_deleted=False)
    # 將商品資料傳入 products.html 模板
    return render(request, 'products.html', {'products': products})


@login_required  # 限制此 view 必須登入才能使用，未登入的使用者會被導向登入頁面
def add_to_cart_2(request, product_id):
    # 使用 get_object_or_404 取得商品，若不存在則回傳 404 錯誤
    # 注意：這裡用 Product.objects，因為即使商品已下架，舊訂單或購物車仍可能需要引用它
    # 嘗試取得商品，這裡用 Product.objects（ActiveProductManager）
    # 只會查詢未下架商品 (is_deleted=False)，下架商品不會被找到
    try:
        product = Product.objects.get(product_id=product_id)
    except Product.DoesNotExist:
        # 如果商品不存在或已下架，顯示錯誤訊息並導回商品列表
        messages.error(request, "此商品已下架或不存在，無法加入購物車。")
        return redirect('product_list')

    # 取得或建立購物車，若使用者沒有購物車就建立一個新的
    cart, created = Cart.objects.get_or_create(user=request.user)

    # 取得或建立購物車項目，若該商品已存在購物車就更新數量
    cart_item, created = CartItem.objects.get_or_create(
        cart=cart,  # 關聯到當前使用者的購物車
        product=product,  # 關聯到商品
        defaults={'quantity': 1, 'price': product.price}  # 預設數量為 1，價格取商品當前價格
    )

    if not created:
        # 如果購物車項目已存在，則數量 +1
        cart_item.quantity += 1
        cart_item.save()  # 儲存更新後的數量
	
	# 顯示成功訊息
    messages.success(request, f"商品「{product.name}」已加入購物車！")
	
    # 完成後導向商品列表頁面
    return redirect('product_list')

@login_required
def add_to_cart(request, product_id):
    """將商品加入購物車，同時檢查庫存"""
    product = get_object_or_404(Product, product_id=product_id)
    cart, created = Cart.objects.get_or_create(user=request.user)

    # 嘗試取得購物車項目，如果沒有就建立
    cart_item, created_item = CartItem.objects.get_or_create(
        cart=cart,
        product=product,
        defaults={'quantity': 1, 'price': product.price}
    )

    if not created_item:
        # 如果已經在購物車，準備增加 1
        new_quantity = cart_item.quantity + 1
        if new_quantity > product.stock:
            messages.error(request, f"庫存不足，最多只能購買 {product.stock} 個")
            return redirect('home')  # 或 redirect('cart_detail')
        cart_item.quantity = new_quantity
        cart_item.save()
        messages.success(request, f"{product.name} 已增加到購物車，數量：{cart_item.quantity}")
    else:
        if product.stock < 1:
            # 如果商品庫存為 0
            cart_item.delete()  # 刪除剛建立的項目
            messages.error(request, f"{product.name} 庫存不足，無法加入購物車")
        else:
            messages.success(request, f"{product.name} 已加入購物車，數量：{cart_item.quantity}")

    return redirect('home')  # 或 redirect('cart_detail')


@login_required
def cart_detail_1(request):
    """
    顯示目前登入使用者的購物車內容
    """

    # 取得使用者購物車
    # 如果不存在就自動建立
    cart, created = Cart.objects.get_or_create(user=request.user)

    # 取得購物車內所有商品
    cart_items = cart.items.all()

    # 計算總金額
    total_price = sum(
        item.price * item.quantity
        for item in cart_items
    )

    # 傳到模板
    return render(
        request,
        'cart.html',
        {
            'cart': cart,
            'cart_items': cart_items,
            'total_price': total_price,
        }
    )

@login_required
def cart_detail(request):

    cart, created = Cart.objects.get_or_create(
        user=request.user
    )

    cart_items = cart.items.all()

    # 每個項目 subtotal
    for item in cart_items:
        item.subtotal = item.price * item.quantity

    # 總金額
    total_price = sum(
        item.subtotal
        for item in cart_items
    )

    return render(
        request,
        'cart.html',
        {
            'cart_items': cart_items,
            'total_price': total_price,
        }
    )

@login_required
@transaction.atomic
def checkout(request):
    """
    購物車結帳功能
    """

    # 取得使用者購物車
    cart = get_object_or_404(Cart, user=request.user)

    # 取得購物車商品
    cart_items = cart.items.all()

    # 如果購物車是空的
    if not cart_items.exists():
        messages.error(request, "購物車是空的，無法結帳。")
        return redirect('cart_detail')

    # 計算訂單總金額
    total_amount = sum(
        item.price * item.quantity
        for item in cart_items
    )

    # 建立 Order
    order = Order.objects.create(
        user=request.user,
        total_amount=total_amount,
        status='pending'
    )

    # 將 CartItem 複製到 OrderItem
    for item in cart_items:

        # 檢查庫存
        if item.product.stock < item.quantity:
            messages.error(
                request,
                f"商品「{item.product.name}」庫存不足。"
            )
            return redirect('cart_detail')

        # 建立訂單項目
        OrderItem.objects.create(
            order=order,
            product=item.product,
            quantity=item.quantity,
            price=item.price,
        )

        # 扣除庫存
        item.product.stock -= item.quantity
        item.product.save()

    # 清空購物車
    cart_items.delete()

    # 成功訊息
    messages.success(request, "訂單建立成功！")

    # 返回首頁
    return redirect('home')


@login_required
def purchased_products(request):
    """
    顯示使用者已購買的商品清單。
    每個訂單包含訂單資訊與其商品列表，每個商品加上小計 subtotal。
    """

    # 取得該使用者所有訂單，依照建立時間排序（最新的在前）
    orders = Order.objects.filter(user=request.user).order_by('-created_at')

    # 建立一個 list，把每個訂單和其商品（含小計）打包
    order_list = []

    for order in orders:
        # 取得該訂單的所有 OrderItem
        # 使用 select_related('product') 避免 N+1 查詢問題
        items = order.items.select_related('product')

        # 建立一個 list 來存每個商品和它的小計
        items_with_subtotal = []

        for item in items:
            # 計算每個商品小計：單價 × 數量
            subtotal = item.price * item.quantity

            # 將 OrderItem 物件和小計一起包成字典
            items_with_subtotal.append({
                'item': item,
                'subtotal': subtotal
            })

        # 將訂單和其商品列表加入 order_list
        order_list.append({
            'order': order,
            'items': items_with_subtotal
        })

    # 將整理好的訂單列表傳給模板
    return render(request, 'purchased_products.html', {'order_list': order_list})

@login_required
def purchased_products_2(request):
    # 取得該使用者所有訂單，依照建立時間排序
    orders = Order.objects.filter(user=request.user).order_by('-created_at')

    # 建立一個 list，把每個訂單和其商品打包
    order_list = []
    for order in orders:
        # 取得該訂單的所有 OrderItem
        items = order.items.select_related('product')  # 預先抓 product 避免 N+1 問題
        order_list.append({
            'order': order,
            'items': items
        })

    return render(request, 'purchased_products.html', {'order_list': order_list})
    
@login_required
def purchased_products_1(request):
    # 抓該使用者所有訂單（不限制 status）
    orders = Order.objects.filter(user=request.user)

    # 取得訂單裡的商品
    products = Product.objects.filter(orderitem__order__in=orders, is_deleted=False).distinct()

    return render(request, 'purchased_products.html', {'products': products})

@login_required
def delete_order(request, order_id):
    """
    刪除使用者自己的訂單流程：
    1. GET：顯示確認刪除頁面
    2. POST：確定刪除訂單，回復商品庫存
    """
    order = get_object_or_404(Order, id=order_id, user=request.user)

    # 無法刪除已付款或已出貨訂單
    if order.status in ['shipped', 'paid']:
        messages.error(request, "無法刪除已出貨或已付款的訂單。")
        return redirect('purchased_products')

    if request.method == 'POST':
        # 開始交易，確保庫存更新和訂單刪除一致
        with transaction.atomic():
            for item in order.items.select_related('product'):
                product = item.product
                product.stock += item.quantity
                product.save()
            order.delete()
        messages.success(request, f"訂單 #{order.order_number} 已刪除，商品庫存已恢復。")
        return redirect('purchased_products')

    # GET：顯示確認刪除頁面
    return render(request, 'confirm_delete_order.html', {'order': order})

@login_required
def delete_order_1(request, order_id):
    """
    刪除使用者自己的訂單。
    只能刪除尚未出貨或已取消的訂單，避免已完成訂單被刪除。
    """
    # 取得訂單或 404
    order = get_object_or_404(Order, id=order_id, user=request.user)

    # 檢查訂單狀態，避免刪除已出貨訂單
    if order.status in ['shipped', 'paid']:
        messages.error(request, "無法刪除已出貨或已付款的訂單。")
        return redirect('purchased_products')

    if request.method == 'POST':
        order.delete()
        messages.success(request, f"訂單 #{order_id} 已刪除。")
        return redirect('purchased_products')

    # 如果是 GET，顯示確認頁面
    return render(request, 'confirm_delete_order.html', {'order': order})

@login_required
def update_cart_item(request, product_id):
    product = get_object_or_404(Product, product_id=product_id)
    
    # 先找出使用者的購物車
    try:
        cart = Cart.objects.get(user=request.user)
    except Cart.DoesNotExist:
        messages.error(request, "購物車不存在")
        return redirect('cart_detail')
        
    # 找到對應的 CartItem
    try:
        cart_item = CartItem.objects.get(cart=cart, product=product)
    except CartItem.DoesNotExist:
        messages.error(request, "購物車中沒有這個商品")
        return redirect('cart_detail')
        

    if request.method == 'POST':
        try:
            quantity = int(request.POST.get('quantity'))
        except (TypeError, ValueError):
            messages.error(request, "數量輸入錯誤")
            return redirect('cart_detail')

        if quantity < 1:
            messages.error(request, "數量不能小於 1")

        elif quantity > product.stock:
            messages.error(request, f"庫存不足，最多只能購買 {product.stock} 個")

        else:
            cart_item.quantity = quantity
            cart_item.save()

            messages.success(
                request,
                f"{product.name} 的數量已更新為 {quantity}"
            )

    return redirect('cart_detail')
    
@login_required
def update_cart_item_1(request, product_id):
    """修改購物車商品數量"""
    product = get_object_or_404(Product, product_id=product_id)
    if request.method == 'POST':
        try:
            quantity = int(request.POST.get('quantity', 1))
        except ValueError:
            messages.error(request, "數量輸入錯誤")
            return redirect('cart_detail')

        if quantity < 1:
            messages.error(request, "數量不能小於 1")
        elif quantity > product.stock:
            messages.error(request, f"庫存不足，最多只能購買 {product.stock} 個")
        else:
            # 取得使用者的購物車項目，沒有就建立
            cart_item, created = CartItem.objects.get_or_create(
                user=request.user,
                product=product,
                defaults={'quantity': quantity, 'price': product.price}
            )
            if not created:
                cart_item.quantity = quantity
                cart_item.save()
            messages.success(request, f"{product.name} 的數量已更新為 {quantity}")

    return redirect('cart_detail')


@login_required
def remove_cart_item(request, product_id):
    """刪除購物車商品"""
    product = get_object_or_404(Product, product_id=product_id)
    
    if request.method == 'POST':
        # 先找使用者的購物車
        try:
            cart = Cart.objects.get(user=request.user)
        except Cart.DoesNotExist:
            messages.error(request, "購物車不存在")
            return redirect('cart_detail')

        # 找出對應的 CartItem
        cart_item = CartItem.objects.filter(cart=cart, product=product).first()
        if cart_item:
            cart_item.delete()
            messages.success(request, f"{product.name} 已從購物車移除")
        else:
            messages.warning(request, f"{product.name} 不在你的購物車中")

    return redirect('cart_detail')


@login_required
def update_cart_item_1(request, item_id):
    """修改購物車商品數量"""
    cart_item = get_object_or_404(CartItem, id=item_id, cart__user=request.user)
    if request.method == 'POST':
        try:
            quantity = int(request.POST.get('quantity', cart_item.quantity))
        except ValueError:
            messages.error(request, "數量輸入錯誤")
            return redirect('cart_detail')

        # 檢查庫存
        if quantity < 1:
            messages.error(request, "數量不能小於 1")
        elif quantity > cart_item.product.stock:
            messages.error(request, f"庫存不足，最多只能購買 {cart_item.product.stock} 個")
        else:
            cart_item.quantity = quantity
            cart_item.save()
            messages.success(request, f"{cart_item.product.name} 的數量已更新為 {quantity}")

    return redirect('cart_detail')


@login_required
def remove_cart_item_1(request, item_id):
    """刪除購物車商品"""
    cart_item = get_object_or_404(CartItem, id=item_id, cart__user=request.user)
    if request.method == 'POST':
        cart_item.delete()
        messages.success(request, f"{cart_item.product.name} 已從購物車移除")

    return redirect('cart_detail')

@login_required
def cart_detail_2(request):
    """購物車頁面"""
    cart_items = CartItem.objects.filter(user=request.user)
    total_price = sum(item.price * item.quantity for item in cart_items)
    return render(request, 'cart.html', {
        'cart_items': cart_items,
        'total_price': total_price
    })
