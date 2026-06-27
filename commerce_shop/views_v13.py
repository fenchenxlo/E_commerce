from django.shortcuts import render, redirect, get_object_or_404  # 匯入 Django 的工具函式：render 用來渲染模板，redirect 用來重新導向，get_object_or_404 用來安全取得資料
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt

from django.contrib.auth.decorators import login_required  # 匯入裝飾器，限制某些 view 必須登入才能使用
from .models import Product, Cart, CartItem, Order, OrderItem, Payment  # 匯入本 app 的模型：商品、購物車、購物車項目
from django.contrib import messages  # 匯入 Django 的訊息框架，用來顯示提示訊息
from django.db import transaction
from django.urls import reverse

import uuid, datetime, hashlib, time, json, traceback
from django.utils import timezone
import urllib.parse
from util.ChkMacVal import generate_check_mac_value
from util.product_image_config import get_product_image

from E_commerce.settings import ECPAY_HASH_KEY,ECPAY_HASH_IV

def home(request):
    # 使用 Product.objects（ActiveProductManager在modols複寫了預設的get_queryset），只會回傳 is_deleted=False 的商品
#     products = Product.objects.all()
    products = list(Product.objects.all())

    for p in products:
        p.image_url = get_product_image(p.regex_name, p.name)
#         print("p.image_url: ",p.image_url)
    # 🔥 重點：幫每個商品「補 image_url」
#     for product in products:
# 
#         product["image_url"] = get_product_image(
#             product["regex_name"],   # 型號判斷
#             product["pname"]         # 顏色判斷
#         )
    
    # 將商品資料傳入 home.html 模板，並以字典形式提供給模板使用
    return render(request, 'home.html', {'products': products})

@login_required
def api_search_product_list(request):
    query = request.GET.get('q','').strip()
    page = int(request.GET.get('page',1))

    #如果沒有搜尋字串,就顯示全部商品
    if query:
        products = Product.objects.filter(regex_name__icontains=query)  |  Product.objects.filter(name__icontains=query)
    else:
        products = Product.objects.all()

    paginator = Paginator(products, 9) #每頁顯示 9 個商品
    current_page = paginator.get_page(page)

    results = [
        {
            'id': p.id,
            'name': p.name,
            'price': p.price,
            'image_url': get_product_image(p.regex_name, p.name)
            }
            for p in current_page.object_list
    ]
    
    return JsonResponse({
        'results': results,
        'has_more': current_page.has_next()
    })

## payment_callback
##商城接收付款通知
@csrf_exempt
@transaction.atomic
def payment_callback(request):

    data = json.loads(request.body)
    print("data:",data)
    recv_mac = data.pop(
        "CheckMacValue"
    )

    local_mac = (
        generate_check_mac_value(data,ECPAY_HASH_KEY,ECPAY_HASH_IV)
    )

    if recv_mac != local_mac:

        return JsonResponse({

            "status":"check_mac_value error"

        }, status=400)
    
    ## 查訂單
    try:
        order = Order.objects.get(order_number=data["merchant_trade_no"])
#         payment = Payment.objects.get(order=order)
        # 建立或更新 Payment 紀錄
        payment, created = Payment.objects.get_or_create(
            order=order,
            transaction_id=data["transaction_id"],
            defaults={
                "amount": data["trade_amt"],
                "payment_method": "ATM",
                "status": "success",
#                 "paid_at": datetime.datetime.strptime(paid_at, "%Y-%m-%d %H:%M:%S"),
                "paid_at": timezone.now(),
                "response_data": dict(request.POST),
                "bank_code": data.get("bank_code"),
                "v_account": data.get("v_account"),
                "expire_date": data.get("expire_date"),
            }
        )
        
    except Payment.DoesNotExist as ex:
        return JsonResponse({
            "status": False,
            "message": str(ex)
        })
    
       
    if data["status"] == "paid":

        order.status = "paid"

        order.save()

        payment.status = "success"

        payment.paid_at = timezone.now()

        payment.response_data = data

        payment.save()

        return JsonResponse({"status":"success"})
    ## 付款失敗
    elif data["status"] == "failed": 

        order.status = "failed"

        order.save()

        payment.status = "failed"

        payment.response_data = data

        payment.save()
        
        return JsonResponse({"status":"failed"})

@csrf_exempt
@login_required
def payment_error(request):

    messages.error(
        request,
        "銀行通知失敗: 虛擬帳號 取得或建立失敗，請稍後再試"
    )

    return redirect('purchased_products')

@login_required
def download_orderPayment_json(request):
    
    return render(request, 'download_order_payment_data.html')

@login_required
def product_list(request):
    # 顯示登入會員自己擁有的商品，並過濾掉下架商品
    products = Product.objects.filter(owner=request.user, is_deleted=False)
    
    # =========================
    # 🔥 圖片對應表（核心）
    # =========================
    IMAGE_MAP = {
        "iPhone 17": "iphone17/i17-白色.jpg",
        "iPhone 17 little Blue": "iphone17/i17-霧藍色.jpg",
        "iPhone 17 little Blue": "iphone17/i17-薰衣草紫色.jpg",
        "iPhone 17 Blue": "iphone17/.jpg",
        "iPhone 17 Black": "iphone17/i17-黑色.jpg",
        "iPhone 17 Pro": "iphone17/i17-pro.jpg",
    }
    
    # 將商品資料傳入 products.html 模板
    return render(request, 'products.html', {'products': products})


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
        order_number = f"ORD-{uuid.uuid4().hex[:10].upper()}",
        shipping_fee = 60,
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

    user = request.user
    
    # 取得該使用者所有訂單，依照建立時間排序（最新的在前）
    orders = Order.objects.filter(user=user).order_by('-created_at')
    
    user_id = user.id
    print("user_id: ",user_id)

    # 建立一個 list，把每個訂單和其商品（含小計）打包
    order_list = []
    
    # 模擬產生 ATM 虛擬帳號與繳費期限
#     bank_code = "013"  # 國泰世華銀行代碼
#     atm_account = f"{bank_code}{random.randint(100000000000, 999999999999)}"
#     expire_date = (datetime.datetime.now() + datetime.timedelta(days=3)).strftime("%Y/%m/%d %H:%M:%S")
    
    for order in orders:
        # 取得該訂單的所有 OrderItem
        # 使用 select_related('product') 避免 N+1 查詢問題
        items = order.items.select_related('product')
        print("order-pay:",order.status)
        # 先取得該訂單的所有 OrderItem
#         order_items = order.items.select_related('product')

        # 把每個商品名稱串起來 (綠界格式通常是 "商品A#商品B#商品C")
        item_names = "#".join([item.product.name for item in items])

        # 建立一個 list 來存每個商品和它的小計
        items_with_subtotal = []
        order_total = 0  # 先建立訂單小計（未加運費）,移到迴圈外,避免每次重設

        for item in items:
            # 計算每個商品小計：單價 × 數量
            subtotal = item.price * item.quantity            

            # 將 OrderItem 物件和小計一起包成字典
            items_with_subtotal.append({
                'item': item,
                'subtotal': subtotal
            })
            
            # 累加訂單商品總額
            order_total += subtotal

        # 固定運費
        shipping_fee = 60

        # 訂單總額（商品小計 + 運費）
        total_with_shipping = order_total + shipping_fee
        
        merchant_id = "shop1234"
        
        # 🔑 打包必要欄位 dict
        payment_payload = {
            'merchant_id': merchant_id,
            'merchant_trade_no': order.order_number,
#             'merchant_trade_date': timezone.localtime().strftime("%Y-%m-%d %H:%M:%S"),  # 自動產生交易時間
            'merchant_trade_date': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), # 自動產生交易時間
            # 'merchant_trade_date': created_at,  # Order交易時間 
            'user_id': user_id,
            'trade_amt': int(total_with_shipping),
            'trade_desc': order.remark or "購買商品",
            'item_name': item_names,
            'choose_payment': "ATM",
            'payment_type': "aio",
            'transaction_id': str(uuid.uuid4()),  # 自動產生唯一交易編號
            'status': order.status,
            # 🔑 綠界官方定義
            'ReturnURL': "http://127.0.0.1:8000/commerce_shop/ecpay_mock_notify/",   # server-to-server callback, # 綠界回傳 URL
            'PaymentInfoUrl': "http://127.0.0.1:8000/commerce_shop/payment_info/",   # 綠界通知商城已取得虛擬帳號
            'OrderResultURL': "http://127.0.0.1:8000/commerce_shop/payment_ok/",  # browser redirect ,瀏覽器跳轉 URL
            'action_url': "http://127.0.0.1:8001/gateway/ecpay_gateway_checkout/",
#             "BankCode": bank_code,
#             "vAccount": atm_account,
#             "ExpireDate": expire_date,
        }
        payment_payload["check_mac_value"] = generate_check_mac_value(payment_payload,ECPAY_HASH_KEY,ECPAY_HASH_IV)

        payment_payload = json.dumps(payment_payload, ensure_ascii=False)
        
        # 將訂單和其商品列表加入 order_list
        order_list.append({
            'order': order,
            'items': items_with_subtotal,
            'shipping_fee': shipping_fee,           # 運費
            'total_with_shipping': total_with_shipping,  # 含運費總額
            'payment_payload': payment_payload,   # ✅ 新增這個 dict
        })

    # 將整理好的訂單列表傳給模板
    return render(request, 'purchased_products.html', {'order_list': order_list})

# @require_POST
@login_required
def ready_form(request):
    """
    商城：
    接收 payment_payload
    組成 HTML Form
    自動 POST 到模擬綠界
    """

    payment_payload = json.loads(request.body)

#     gateway_url = "http://127.0.0.1:8001/gateway/ecpay_gateway_checkout/"

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>轉址到綠界中...</title>
    </head>
    <body>
        <h2>正在導向綠界付款...</h2>
        <form id="ecpayForm"
              method="post"
              action="{payment_payload['action_url']}">
    """

    for key, value in payment_payload.items():

        html += f"""
            <input
                type="hidden"
                name="{key}"
                value="{value}">
        """

    html += """
        </form>

        <script>
            document.getElementById(
                "ecpayForm"
            ).submit();
        </script>

    </body>
    </html>
    """

    return HttpResponse(html)

def ready_form1(request):
    # 🔑 打包必要欄位 dict
    payment_payload = {
        "MerchantID": merchant_id,
        "MerchantTradeNo": order.order_number,
        "MerchantTradeDate": timezone.localtime().strftime("%Y/%m/%d %H:%M:%S"),  # 自動產生交易時間
        "UserId": user_id,
        "TradeAmt": int(total_with_shipping),
        "TradeDesc": order.remark or "購買商品",
        "ItemName": item_names,
        "ChoosePayment": "ATM",
        "PaymentType": "aio",
        "TransactionID": str(uuid.uuid4()),  # 自動產生唯一交易編號
        "Status": order.status,
        # 🔑 綠界官方定義
        "ReturnURL": "http://127.0.0.1:8000/commerce_shop/ecpay_mock_notify/",   # server-to-server callback, # 綠界回傳 URL
        "PaymentInfoUrl": "http://127.0.0.1:8000/commerce_shop/ready_form/",   # 綠界通知商城已取得虛擬帳號
        "OrderResultURL": "http://127.0.0.1:8000/commerce_shop/payment_ok/",  # browser redirect ,瀏覽器跳轉 URL
#             "BankCode": bank_code,
#             "vAccount": atm_account,
#             "ExpireDate": expire_date,
    }
    payment_payload = {
        "MerchantID": "3002607",
        "MerchantTradeNo": "ORDER202605280001",
        "MerchantTradeDate": "2026/05/28 12:30:00",
        "TradeAmt": 1000,
        "TradeDesc": "購買商品",
        "ItemName": "測試商品",
        "PaymentType": "ATM",
        "ReturnURL": "http://127.0.0.1:8000/commerce_shop/ecpay_mock_notify/",
        "OrderResultURL": "http://127.0.0.1:8000/commerce_shop/payment-ok/",
    }
    # 產生 CheckMacValue
    payment_payload["CheckMacValue"] = generate_check_mac_value(payment_payload)
    return render(request, "auto_submit_form.html", {
        "action_url": "http://localhost:8001/gateway/createOrder/",
        "params": payment_payload
    })


@login_required
def delete_order_item(request, order_item_id):
    """
    刪除「單一商品列（OrderItem）」並恢復庫存
    """

    # 🔥 取得「單一商品列」，不是整張訂單
    item = get_object_or_404(
        OrderItem,
        id=order_item_id,
        order__user=request.user   # 確保只能刪自己的訂單商品
    )

    order = item.order  # 取得對應訂單

    # ❗如果訂單已付款或已出貨 → 不允許刪
    if order.status in ['shipped', 'paid']:
        messages.error(request, "已付款或已出貨的訂單商品無法刪除。")
        return redirect('purchased_products')

    # 🔥 POST 才真正刪除
    if request.method == 'POST':

        with transaction.atomic():

            # 🔥 1. 先恢復庫存（只針對這一個商品）
            product = item.product
            product.stock += item.quantity
            product.save()

            # 🔥 2. 刪除這一個 OrderItem（不是整張訂單）
            item.delete()

            # 🔥 3. 如果這張訂單已經沒有任何商品 → 可選：刪訂單
            if not order.items.exists():
                order.delete()

        messages.success(request, "商品已成功從訂單移除")
        return redirect('purchased_products')

    # GET：確認頁面（可選）
    return render(request, 'confirm_delete_item.html', {
        'item': item
    })
	
	
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

#=====================================================================================================================
#e_comm_ecpay_mock
@csrf_exempt
def ecpay_mock_notify(request):
    if request.method == "POST":
        # 取出綠界回傳的欄位
        merchant_trade_no = request.POST.get("MerchantTradeNo")  # 商城訂單編號
        trade_no = request.POST.get("TradeNo")                   # 綠界交易編號
        trade_amt = request.POST.get("TradeAmt")                 # 交易金額
        payment_date = request.POST.get("PaymentDate")           # 付款完成時間
        payment_type = request.POST.get("PaymentType")           # 付款方式
        rtn_code = request.POST.get("RtnCode")                   # 回傳代碼 (1=成功)
        rtn_msg = request.POST.get("RtnMsg")                     # 回傳訊息

        try:
            # 找到商城的訂單
            order = Order.objects.get(order_number=merchant_trade_no)
        except Order.DoesNotExist:
            return HttpResponse("0|Order Not Found")

        # 更新訂單狀態
        if rtn_code == "1":  # 成功
            order.status = "paid"
            order.save()

            # 建立或更新 Payment 紀錄
            payment, created = Payment.objects.get_or_create(
                order=order,
                transaction_id=trade_no,
                defaults={
                    "amount": trade_amt,
                    "payment_method": payment_type,
                    "status": "success",
                    "paid_at": datetime.datetime.strptime(payment_date, "%Y-%m-%d %H:%M:%S"),
                    "response_data": dict(request.POST),
                }
            )
            if not created:
                # 如果已存在，更新狀態
                payment.status = "success"
                payment.paid_at = datetime.datetime.strptime(payment_date, "%Y-%m-%d %H:%M:%S")
                payment.response_data = dict(request.POST)
                payment.save()

        else:  # 失敗
            order.status = "cancelled"
            order.save()

            Payment.objects.create(
                order=order,
                transaction_id=trade_no,
                amount=trade_amt,
                payment_method=payment_type,
                status="failed",
                response_data=dict(request.POST),
            )

        # ✅ 綠界規範：必須回傳 "1|OK"
        return HttpResponse("1|OK")

    return HttpResponse("0|Invalid Method")

@login_required
@csrf_exempt
@transaction.atomic
def payment_ok(request):

    if request.method != "POST":
        return HttpResponse("Method Not Allowed", status=405)
#         return HttpResponse("method error")

    try:            
        payment_payload = request.POST.dict() if request.POST else request.body
        print("1")
        # 如果商城端用 JSON 傳送
        if isinstance(payment_payload, (bytes, bytearray)):
            payment_payload = json.loads(payment_payload.decode("utf-8"))
            print("payment_payload: ",payment_payload)
    except Exception as e:
        print(f"發生錯誤:{e}")
        print("="*50)
        error = traceback.print_exc()
        return HttpResponseBadRequest(error)

    print("2")
    
    received_mac = payment_payload.copy()

    received_mac = received_mac.pop("check_mac_value","")
    payment_payload1 = payment_payload.pop("check_mac_value","")
    expected_mac = generate_check_mac_value(
        payment_payload,
        settings.ECPAY_HASH_KEY,
        settings.ECPAY_HASH_IV
    )

    print("received_mac =", received_mac)
    print("expected_mac =", expected_mac)
    print("payment_payload =", payment_payload)    
    
    if received_mac != expected_mac:
        return HttpResponse(
            "CheckMacValue Error",
            status=400
        )
    
    merchant_trade_no = payment_payload.get("merchant_trade_no") # 訂單編號
    merchant_trade_date = payment_payload.get("merchant_trade_date") # 訂單日期
    trade_no = payment_payload.get("trade_no")                  # 交易編號
    trade_amt = payment_payload.get("trade_amt")                 # 交易金額
    paid_at = payment_payload.get("order_pay_at")           # 付款完成時間
    payment_method = payment_payload.get("choose_payment")           # 付款方式
    
       
    try:
        # 找到商城的訂單
        order = Order.objects.get(order_number=merchant_trade_no)
#         orders = Order.objects.filter(order_number=merchant_trade_no).order_by("-created_at")
        order.status = "paid"
        order.save()
    except Order.DoesNotExist:
        return HttpResponse("0|Order Not Found")
    
    
    # 建立或更新 Payment 紀錄
    payment, created = Payment.objects.get_or_create(
        order=order,
        transaction_id=trade_no,
        defaults={
            "amount": trade_amt,
            "payment_method": payment_method,
            "status": "success",
            "paid_at": datetime.datetime.strptime(paid_at, "%Y-%m-%d %H:%M:%S"),
            "response_data": dict(request.POST),
            "bank_code": payment_payload.get("bank_code"),
            "v_account": payment_payload.get("v_account"),
            "expire_date": payment_payload.get("expire_date"),
        }
    )
    print("created: ",created)
#     if not created:
#         # 如果已存在，更新狀態
#         payment.status = "success"
#         payment.paid_at = datetime.datetime.strptime(payment_date, "%Y-%m-%d %H:%M:%S")
#         payment.response_data = dict(request.POST)
#         payment.save()
    # 返回首頁
#     return redirect('home')

    user = request.user
    
    # 取得該使用者所有訂單，依照建立時間排序（最新的在前）
    orders = Order.objects.filter(user=user).order_by('-created_at')
    
    user_id = user.id
    print("user_id: ",user_id)

    order_list = []
    for order in orders:
        # 取得該訂單的所有 OrderItem
        # 使用 select_related('product') 避免 N+1 查詢問題
        items = order.items.select_related('product')
        print("order-pay:",order.status)
        # 先取得該訂單的所有 OrderItem
#         order_items = order.items.select_related('product')

        # 把每個商品名稱串起來 (綠界格式通常是 "商品A#商品B#商品C")
        item_names = "#".join([item.product.name for item in items])

        # 建立一個 list 來存每個商品和它的小計
        items_with_subtotal = []
        order_total = 0  # 先建立訂單小計（未加運費）,移到迴圈外,避免每次重設

        for item in items:
            # 計算每個商品小計：單價 × 數量
            subtotal = item.price * item.quantity
#            order_total = 0  # 先建立訂單小計（未加運費）

            # 將 OrderItem 物件和小計一起包成字典
            items_with_subtotal.append({
                'item': item,
                'subtotal': subtotal
            })
            
            # 累加訂單商品總額
            order_total += subtotal

        # 固定運費
        shipping_fee = 60

        # 訂單總額（商品小計 + 運費）
        total_with_shipping = order_total + shipping_fee
        
        merchant_id = "shop1234"
        
        # 🔑 打包必要欄位 dict
        payment_payload = {
            'merchant_id': merchant_id,
            'merchant_trade_no': order.order_number,
            'merchant_trade_date': merchant_trade_date,  # 訂單日期 
            # 'merchant_trade_date': created_at,  # Order交易時間 
            'user_id': user_id,
            'trade_amt': int(total_with_shipping),
            'trade_desc': order.remark or "購買商品",
            'item_name': item_names,
            'choose_payment': "ATM",
            'payment_type': "aio",
            'transaction_id': str(uuid.uuid4()),  # 自動產生唯一交易編號
            'status': order.status,
            # 🔑 綠界官方定義
            'ReturnURL': "http://127.0.0.1:8000/commerce_shop/ecpay_mock_notify/",   # server-to-server callback, # 綠界回傳 URL
            'PaymentInfoUrl': "http://127.0.0.1:8000/commerce_shop/payment_info/",   # 綠界通知商城已取得虛擬帳號
            'OrderResultURL': "http://127.0.0.1:8000/commerce_shop/payment_ok/",  # browser redirect ,瀏覽器跳轉 URL
            'action_url': "http://127.0.0.1:8001/gateway/ecpay_gateway_checkout/",
#             "BankCode": bank_code,
#             "vAccount": atm_account,
#             "ExpireDate": expire_date,
        }
        payment_payload["check_mac_value"] = generate_check_mac_value(payment_payload,ECPAY_HASH_KEY,ECPAY_HASH_IV)

        payment_payload = json.dumps(payment_payload, ensure_ascii=False)
        
        # 將訂單和其商品列表加入 order_list
        order_list.append({
            'order': order,
            'items': items_with_subtotal,
            'shipping_fee': shipping_fee,           # 運費
            'total_with_shipping': total_with_shipping,  # 含運費總額
            'payment_payload': payment_payload,   # ✅ 新增這個 dict
        })
    
    # 把訂單資料丟給 purchased_products.html
    return render(request, "purchased_products.html", {
        "order_list": order_list
    })

#======================================================================================================================

@login_required
def create_fake_ecpay_payment(request, order_id):

    """
    建立 Fake 綠界付款

    流程：

    1. 找到訂單
    2. 建立 Payment
    3. 產生 fake payment url
    4. redirect 到假付款頁
    """

    # 只能付款自己的訂單
    order = get_object_or_404(
        Order,
        id=order_id,
        user=request.user
    )

    # 避免重複付款
#     if hasattr(order, 'payment'):
#         messages.warning(request, "此訂單已建立付款")
#         return redirect('purchased_products')
    # 避免重複付款（但允許失敗交易再次付款）
    if hasattr(order, 'payment') and order.payment.status != 'failed':
        messages.warning(request, "此訂單已建立付款")
        return redirect('purchased_products')

    # 建立 transaction id
    transaction_id = f"TXN-{uuid.uuid4().hex[:12].upper()}"

    # 建立 fake payment url : 會自動幫你組：/commerce_shop/fake-ecpay/cashier/xxx
    payment_url = request.build_absolute_uri(
        reverse(
            'fake_ecpay_cashier',
            args=[transaction_id]
        )
    )
    print("payment_url: ",payment_url)

    # 建立 Payment
    payment = Payment.objects.create(
        order=order,
        transaction_id=transaction_id,
        amount=order.total_amount,
        status='pending',
        payment_method='fake_ecpay',
        payment_url=payment_url
    )

    # 導向 fake 綠界付款頁
    return redirect(payment_url)


@login_required
def fake_ecpay_cashier(request, transaction_id):

    """
    Fake 綠界付款頁

    模擬：

    1. 信用卡付款
    2. 付款成功
    3. 付款失敗
    """

    payment = get_object_or_404(
        Payment,
        transaction_id=transaction_id
    )

    return render(
        request,
        'fake_ecpay_cashier.html',
        {
            'payment': payment
        }
    )

@csrf_exempt
def fake_ecpay_callback(request):

    """
    Fake 綠界 callback
    # Fake 綠界 callback（模擬金流平台回呼你的網站）
    模擬：

    綠界 Server -> 你的網站 webhook
    """

    # ⚠️ 綠界/金流 webhook 一定是 POST
    # 用 POST 才能帶交易資料進來
    if request.method == "POST":

        # 取得交易編號（用來找到對應 Payment）
        transaction_id = request.POST.get('transaction_id')

        # 取得付款結果（success / failed）
        payment_status = request.POST.get('status')

        # 用 transaction_id 找出對應的 Payment 紀錄
#         payment = Payment.objects.get(transaction_id=transaction_id)
        try:
            payment = Payment.objects.get(transaction_id=transaction_id)
        except Payment.DoesNotExist:
            return HttpResponse("Payment not found", status=404)

        # =========================
        # 付款成功流程
        # =========================
        if payment_status == 'success':

            # 更新付款狀態為成功
            payment.status = 'success'

            # 記錄付款時間（現在時間）
            payment.paid_at = timezone.now()

            # 存入 callback 原始資料（方便 debug / log）
            payment.save()

            # 取得對應訂單
            order = payment.order

            # 更新訂單狀態為已付款
            order.status = 'paid'

            # 儲存訂單狀態
            order.save()

        # =========================
        # 付款失敗流程
        # =========================
        else:

            # 更新付款狀態為失敗
            payment.status = 'failed'

            # 儲存付款結果
            payment.save()

        # =========================
        # 關鍵重點（很重要）
        # =========================
        # callback 本質是「背景通知」
        # 不是給使用者看的頁面

        # 所以這裡 redirect 使用者回訂單頁
        # 讓他看到付款結果
        return redirect('purchased_products')

    # 如果不是 POST（例如有人直接用瀏覽器打網址）
    return HttpResponse("Invalid")



# ================================
# 真 綠界金流 ECPay 付款功能
# ================================

# 產生 CheckMacValue
# 綠界規定必須產生此驗證碼
# 用來驗證資料沒有被竄改
def generate_check_mac_value(params, hash_key, hash_iv):

    # 依照參數名稱排序（綠界規定）
    sorted_params = sorted(params.items())

    # 前面加上 HashKey
    raw = f"HashKey={hash_key}"

    # 將所有參數串接起來
    for k, v in sorted_params:
        raw += f"&{k}={v}"

    # 最後加上 HashIV
    raw += f"&HashIV={hash_iv}"

    # URL encode 並轉小寫
    raw = urllib.parse.quote_plus(raw).lower()

    # 綠界特殊轉換規則
    replacements = {
        '%2d': '-',
        '%5f': '_',
        '%2e': '.',
        '%21': '!',
        '%2a': '*',
        '%28': '(',
        '%29': ')'
    }

    # 進行特殊字元替換
    for key, value in replacements.items():
        raw = raw.replace(key, value)

    # SHA256 加密後轉大寫
    return hashlib.sha256(
        raw.encode('utf-8')
    ).hexdigest().upper()


@login_required
def create_ecpay_payment(request, order_id):

    """
    建立綠界付款

    流程：

    1. 使用者點擊付款
    2. 建立 Payment 紀錄
    3. 產生綠界付款參數
    4. 自動導向綠界付款頁面
    """

    # 取得訂單
    order = get_object_or_404(
        Order,
        id=order_id,
        user=request.user
    )

    # 如果訂單已付款
    if order.status == 'paid':

        messages.warning(request, "此訂單已付款")

        return redirect('purchased_products')

    # 建立交易編號
    # 綠界 MerchantTradeNo 不可重複
    merchant_trade_no = f"ORDER{int(time.time())}"

    # 綠界付款參數
    params = {

        # 商店編號（綠界提供）
        "MerchantID": settings.ECPAY_MERCHANT_ID,

        # 商店交易編號（不可重複）
        "MerchantTradeNo": merchant_trade_no,

        # 交易時間
        "MerchantTradeDate": time.strftime(
            "%Y/%m/%d %H:%M:%S"
        ),

        # 固定 aio
        "PaymentType": "aio",

        # 總金額
        "TotalAmount": int(order.total_amount),

        # 交易描述
        "TradeDesc": "Django Shop Payment",

        # 商品名稱
        "ItemName": "商城商品付款",

        # 綠界付款完成後通知 Django 的 API
        # 正式環境請改成你的網域
        "ReturnURL": "https://你的domain/payment/callback/",

        # 付款方式
        # Credit = 信用卡
        "ChoosePayment": "Credit",

        # 加密方式
        "EncryptType": 1,
    }

    # 產生 CheckMacValue
    check_mac_value = generate_check_mac_value(
        params,
        settings.ECPAY_HASH_KEY,
        settings.ECPAY_HASH_IV
    )

    # 加入參數
    params["CheckMacValue"] = check_mac_value

    # 建立 Payment 紀錄
    payment = Payment.objects.create(
        order=order,

        # 綠界交易編號
        transaction_id=merchant_trade_no,

        # 金額
        amount=order.total_amount,

        # 初始狀態
        status='pending'
    )

    # 建立 HTML form
    # 自動 POST 到綠界付款頁
    html = f"""
    <html>
    <body>

        <form id='ecpay-form'
              method='post'
              action='https://payment-stage.ecpay.com.tw/Cashier/AioCheckOut/V5'>

            {''.join([
                f"<input type='hidden' name='{k}' value='{v}'>"
                for k, v in params.items()
            ])}

        </form>

        <script>
            // 自動送出表單
            document.getElementById('ecpay-form').submit();
        </script>

    </body>
    </html>
    """

    return HttpResponse(html)


# csrf_exempt：
# 綠界 POST callback 時不會帶 csrf token
# 所以必須關閉 csrf 驗證
@csrf_exempt
def ecpay_callback(request):

    """
    綠界付款完成後 callback API

    綠界會 POST 回來：

    MerchantTradeNo
    RtnCode
    付款資訊

    Django 收到後：

    1. 更新 Payment 狀態
    2. 更新 Order 狀態
    """

    # 取得綠界交易編號
    merchant_trade_no = request.POST.get(
        "MerchantTradeNo"
    )

    # 取得付款結果
    # 1 = 成功
    rtn_code = request.POST.get("RtnCode")

    try:

        # 找出對應 Payment
        payment = Payment.objects.get(
            transaction_id=merchant_trade_no
        )

        # 付款成功
        if rtn_code == "1":

            # 更新付款狀態
            payment.status = "success"

            # 儲存綠界回傳資料
            payment.response_data = dict(
                request.POST
            )

            payment.save()

            # 更新訂單狀態
            order = payment.order

            order.status = "paid"

            order.save()

        else:

            # 付款失敗
            payment.status = "failed"

            payment.save()

        # 綠界規定：
        # 必須回傳 1|OK
        return HttpResponse("1|OK")

    except Payment.DoesNotExist:

        # 找不到付款資料
        return HttpResponse("0|Fail")
