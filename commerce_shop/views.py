from django.shortcuts import render, redirect, get_object_or_404  # 匯入 Django 的工具函式：render 用來渲染模板，redirect 用來重新導向，get_object_or_404 用來安全取得資料
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt

from django.contrib.auth.decorators import login_required  # 匯入裝飾器，限制某些 view 必須登入才能使用
from .models import Product, Cart, CartItem, Order, OrderItem, Payment	# 匯入本 app 的模型：商品、購物車、購物車項目
from django.contrib import messages	 # 匯入 Django 的訊息框架，用來顯示提示訊息
from django.db import connection, transaction
from django.urls import reverse

import uuid, datetime, hashlib, time, json, traceback
from django.utils import timezone
import urllib.parse
from util.ChkMacVal import generate_check_mac_value
from util.product_image_config import get_product_image

from E_commerce.settings import ECPAY_HASH_KEY,ECPAY_HASH_IV
from django.core.paginator import Paginator
import re
from django.db.models import Q
from django.contrib.auth.decorators import user_passes_test
import logging			# 【新增】

logger = logging.getLogger(__name__)   # 【新增】

HF_SPACE_E_COMMERCE_URL = settings.HF_SPACE_E_COMMERCE_URL
HF_SPACE_ECPAY_MOCK_URL = settings.HF_SPACE_ECPAY_MOCK_URL
ECPAY_HASH_KEY = settings.ECPAY_HASH_KEY
ECPAY_HASH_IV = settings.ECPAY_HASH_IV
BACKEND_URL = settings.BACKEND_URL

def _log_and_build_error_response(view_name, exception, status=500):
	"""
	共用錯誤處理小工具:
	- 【修改】改用 logging 模組的 logger.exception(),而不是 print() + traceback.format_exc()。
	  logger.exception() 會自動把目前例外的完整 traceback 一起記錄下來,
	  而且透過標準 logging 機制輸出,在 HF Space 的 Logs 分頁能穩定被抓到
	  (print() 在某些情況下可能因為 stdout 緩衝或多執行緒交錯而漏看或亂序)。
	- 回傳統一格式的 JSON 錯誤訊息給前端,包含：
		error_type	→ Python 例外類別名稱(例如 KeyError, IntegrityError)
		message		→ 例外的詳細訊息
		view		→ 是在哪個 view 發生的,方便定位問題
	"""
	error_type = type(exception).__name__
	error_message = str(exception)
	logger.exception(f"[{view_name}] {error_type}: {error_message}")  # 【修改】
	return JsonResponse(
		{
			"status": "error",
			"view": view_name,
			"error_type": error_type,
			"message": error_message,
		},
		status=status,
	)
	
def home(request):
	# 使用 Product.objects（ActiveProductManager在modols複寫了預設的get_queryset），只會回傳 is_deleted=False 的商品
#	  products = Product.objects.all()
	products = list(Product.objects.all())

	for p in products:
		p.image_url = get_product_image(p.regex_name, p.name)
#		  print("p.image_url: ",p.image_url)
	# 🔥 重點：幫每個商品「補 image_url」
#	  for product in products:
# 
#		  product["image_url"] = get_product_image(
#			  product["regex_name"],   # 型號判斷
#			  product["pname"]		   # 顏色判斷
#		  )
	
	# 將商品資料傳入 home.html 模板，並以字典形式提供給模板使用
	return render(request, 'home.html', {'products': products})

#@login_required
def api_search(request):

	query = request.GET.get('q', '').strip()
	page = int(request.GET.get('page', 1))

	# ==========================
	# 修改開始
	# ==========================

	if query:

		# -----------------------------------
		# 修改：
		# 統一轉小寫
		# -----------------------------------
		query_lower = query.lower()

		# -----------------------------------
		# 修改：
		# 支援以下分隔符號
		#
		# 空白
		# -
		# /
		# \
		# ,
		# (
		# )
		#
		# 例如：
		# iphone-17/pro(256g)-銀色
		#
		# 會拆成：
		# ['iphone','17','pro','256g','銀色']
		# -----------------------------------
		words = [
			w.lower()
			for w in re.split(
				r'[\s,\-\/\\\(\)]+',
				query
			)
			if w
		]

		# -----------------------------------
		# 關鍵字少於3個
		# 模糊搜尋
		# -----------------------------------
		if len(words) < 3:

			products = (
				Product.objects.filter(
					Q(regex_name__icontains=query)
					|
					Q(name__icontains=query)
				)
			).distinct()

		# -----------------------------------
		# 關鍵字3個以上
		# AND搜尋
		# -----------------------------------
		else:

			q_obj = Q()

			for word in words:

				q_obj &= (
					Q(name__icontains=word)
					|
					Q(regex_name__icontains=word)
				)

			products = (
				Product.objects.filter(q_obj)
				.distinct()
			)

		# ==================================================
		# 修改：
		# Pro / Pro Max 判斷
		#
		# iphone 17 pro
		# -> 不顯示 Pro Max
		#
		# iphone 17 pro max
		# -> 只顯示 Pro Max
		# ==================================================

		if "pro" in words and "max" in words:

			products = products.filter(
				Q(name__icontains="pro max")
				|
				Q(regex_name__icontains="pro max")
			)

		elif "pro" in words:

			products = products.exclude(
				Q(name__icontains="pro max")
				|
				Q(regex_name__icontains="pro max")
			)

		# ==================================================
		# 容量精確判斷
		# ==================================================

		capacities = [
			"128g",
			"256g",
			"512g",
			"1tb",
			"2tb"
		]

		for cap in capacities:

			if cap in words:

				products = products.filter(
					Q(name__icontains=cap)
					|
					Q(regex_name__icontains=cap)
				)

				break

		products = products.order_by('product_id')

	else:

		products = Product.objects.all().order_by('product_id')

	# ==========================
	# 修改結束
	# ==========================

	paginator = Paginator(products, 12)

	current_page = paginator.get_page(page)

	results = [
		{
			'product_id': p.product_id,
			'name': p.name,
			'price': p.price,
			'stock': p.stock,
			'image_url': get_product_image(
				p.regex_name,
				p.name
			)
		}
		for p in current_page.object_list
	]

	return JsonResponse({
		'results': results,
		'has_more': current_page.has_next()
	})

def is_admin(user):
	"""判斷是否為已登入的管理員(superuser)"""
	return user.is_authenticated and user.is_superuser


@user_passes_test(is_admin, login_url='/admin/login/')
def db_query_tool(request):
	"""
	資料庫查詢工具:
	流程 —— 使用者先選擇 table,選定後列出該 table 所有欄位,
	再選擇「兩個」欄位(column1、column2),查詢這兩個欄位
	「同一列(同一筆資料)」對應的值,例如 order_number 對應 status。
	重點:兩個欄位必須放在同一個 SELECT 裡一起查,才能保證
	回傳的每一筆 (col1值, col2值) 確實來自同一列資料,
	而不是像分開查兩次那樣,兩份清單各自篩選、順序對不上。
	"""
	tables = []			 # 所有可查詢的 table 名稱
	columns = []		  # 目前選定 table 的欄位名稱清單
	rows = []			   # 查詢結果,每筆是 (col1值, col2值) 的 tuple
	error = None		   # 查詢過程中若有錯誤,存放錯誤訊息

	table_choice = request.GET.get('table', '')		 # 使用者選擇的 table 名稱
	column1_choice = request.GET.get('column1', '')	 # 使用者選擇的第一個欄位
	column2_choice = request.GET.get('column2', '')	 # 使用者選擇的第二個欄位

	with connection.cursor() as cursor:
		# 1. 取得資料庫中所有「業務用」table
		#	 排除 sqlite 系統表、django 內建表、auth 相關表,避免查到不該看的系統資料
		cursor.execute(
			"SELECT name FROM sqlite_master WHERE type='table' "
			"AND name NOT LIKE 'sqlite_%' "
			"AND name NOT LIKE 'django_%' "
			"AND name NOT LIKE 'auth_%';"
		)
		tables = [r[0] for r in cursor.fetchall()]

		# 2. 若使用者有選擇 table,且該 table 確實存在於允許清單中
		#	 (白名單檢查,防止使用者從網址列竄改 table 參數)
		if table_choice and table_choice in tables:
			# 2-1. 取得該 table 的所有欄位名稱(給使用者選擇用)
			cursor.execute(f"PRAGMA table_info({table_choice});")
			columns = [r[1] for r in cursor.fetchall()]

			# 3. 兩個欄位都要有選,且都存在於這個 table 的欄位清單中(白名單檢查),
			#	 且不能選成同一個欄位(對應兩個一樣的東西沒有意義)
			if (column1_choice and column2_choice
					and column1_choice in columns
					and column2_choice in columns
					and column1_choice != column2_choice):
				try:
					# 3-1. 關鍵修改:col1、col2 放在同一個 SELECT 裡一起撈,
					#	   確保同一列回傳的兩個值是「同一筆資料」的對應值。
					#	   table_choice / column1_choice / column2_choice
					#	   都已經過白名單檢查,用 f-string 組 SQL 是安全的。
					#	   加上 ORDER BY rowid,確保每次查詢順序固定一致。
					query = (
						f"SELECT {column1_choice}, {column2_choice} "
						f"FROM {table_choice} "
						f"WHERE {column1_choice} IS NOT NULL "
						f"AND {column2_choice} IS NOT NULL "
						f"ORDER BY rowid;"
					)
					cursor.execute(query)
					# 直接存成 tuple list:[(col1值, col2值), (col1值, col2值), ...]
					rows = [(r[0], r[1]) for r in cursor.fetchall()]
				except Exception as e:
					# 查詢過程中若發生錯誤(例如欄位型別問題),記錄錯誤訊息
					error = str(e)

	context = {
		'tables': tables,
		'columns': columns,
		'rows': rows,
		'error': error,
		'table_choice': table_choice,
		'column1_choice': column1_choice,
		'column2_choice': column2_choice,
	}
	return render(request, 'admin_tools/db_query.html', context)

@csrf_exempt
def cod_store_confirmed(request):
	"""
	【新增】接收 ecpay_mock(cod_gateway)的 server-to-server 通知:
	使用者已確認超商取貨付款的取貨門市,這裡把結果寫回本地 Order,
	讓「已購買商品清單」頁面能顯示「已確認超商取貨付款」,
	不再繼續顯示「選擇付款方式」的按鈕(避免使用者已經選完又重複選)。

	容易出錯的地方(JSON 解析、簽章驗證、找不到訂單)都各自攔截,
	印出完整錯誤方便在 HF Space Logs 除錯。
	"""
	if request.method != "POST":
		return HttpResponse("method error", status=405)

	# ── Step 1: 解析請求 body ──────────────────────────
	try:
		data = json.loads(request.body)
	except json.JSONDecodeError as e:
#		 print(f"❌ [cod_store_confirmed.parse_body] {type(e).__name__}: {e}")
		logger.exception("❌ [cod_store_confirmed.parse_body] JSON 格式錯誤 {type(e).__name__}: {e}")	# 【修改】
		return JsonResponse({"status": "error", "message": "JSON 格式錯誤"}, status=400)

	# ── Step 2: 驗證 CheckMacValue,防止被偽造請求竄改訂單狀態 ──
	try:
		recv_mac = data.pop("check_mac_value", "")
		local_mac = generate_check_mac_value(data, ECPAY_HASH_KEY, ECPAY_HASH_IV)
	except Exception as e:
#		print(f"❌ [cod_store_confirmed.generate_mac] {type(e).__name__}: {e}")
		logger.exception("[cod_store_confirmed.generate_mac] 簽章計算失敗 {type(e).__name__}: {e}")  # 【修改】
		return JsonResponse({"status": "error", "message": str(e)}, status=400)

	if recv_mac != local_mac:
#		print(f"⚠️ [cod_store_confirmed] CheckMacValue 不符,拒絕這次通知")
		logger.warning("⚠️ [cod_store_confirmed] CheckMacValue 不符,拒絕這次通知")  # 【修改】
		return JsonResponse({"status": "error", "message": "CheckMacValue Error"}, status=400)

	# ── Step 3: 找出對應訂單 ────────────────────────────
	try:
		order = Order.objects.get(order_number=data["merchant_trade_no"])
	except Order.DoesNotExist as e:
#		print(f"❌ [cod_store_confirmed.order_not_found] {type(e).__name__}: {e}")
		logger.exception("❌  [cod_store_confirmed.order_not_found] 找不到對應訂單 {type(e).__name__}: {e}")  # 【修改】
		return JsonResponse({"status": "error", "message": "找不到對應訂單"}, status=404)
	except KeyError as e:
		print(f"❌ [cod_store_confirmed.missing_field] 缺少欄位: {e}")
		logger.exception(f"❌ [cod_store_confirmed.missing_field] 缺少欄位: {e}")  # 【修改】
		return JsonResponse({"status": "error", "message": f"缺少欄位: {e}"}, status=400)
	except Exception as e:
#		print(f"❌ [cod_store_confirmed.db_read_unexpected] {type(e).__name__}: {e}")
		logger.exception("❌ [cod_store_confirmed.db_read_unexpected] 讀取訂單失敗")  # 【修改】
		return JsonResponse({"status": "error", "message": str(e)}, status=500)

	# ── Step 4: 寫回訂單的付款方式與門市資訊 ───────────────
	try:
		order.payment_method = "COD"
		order.cvs_store_name = data.get("store_name", "")
		order.cvs_store_address = data.get("store_address", "")
		order.save()
	except Exception as e:
#		print(f"❌ [cod_store_confirmed.db_write] {type(e).__name__}: {e}")
		logger.exception("❌ [cod_store_confirmed.db_write] 寫入訂單失敗 {type(e).__name__}: {e}")  # 【修改】
		return JsonResponse({"status": "error", "message": str(e)}, status=500)

	return JsonResponse({"status": "success"})

@login_required
def enter_receiver_info(request, order_number):
    """
    【新增】「前往付款」的中間頁:填寫/確認收件人姓名、手機、地址,並選擇付款方式(ATM/COD)。

    GET:  顯示表單,預填 Order 目前既有的收件資訊
    POST: 1. 驗證欄位
          2. 把收件資訊存回 Order
          3. 用「剛存進去的最新資料」組出對應付款方式的 payload 並簽章
          4. 直接 render 一個會自動送出的 HTML form,POST 到 ecpay_mock 的 action_url
             (整段「送到綠界」直接在這裡完成,純傳統 Django 表單流程,不用 JS/fetch,
             降低出錯機會,也比較好除錯)

    容易出錯的地方都各自用 try/except 包住:
      - 訂單查詢(get_object_or_404 本身若查不到會自動回 404,不用額外包)
      - 表單欄位驗證(必填檢查)
      - 資料庫寫入(order.save())
      - 商品明細/金額計算(items 可能是空的、product 可能被刪除等)
      - payload 組裝與簽章計算
    每個例外都用 logger.exception() 記錄完整 traceback,方便在 HF Space Logs 分頁除錯。
    """
    # 只能操作自己的訂單,且只有還沒確認付款方式的狀態才能進來這頁,
    # 避免使用者用網址列亂改 order_number 存取別人的訂單,或修改已經走完流程的訂單
    order = get_object_or_404(
        Order,
        order_number=order_number,
        user=request.user,
        status__in=["pending", "failed"],
    )

    # ── GET:單純顯示表單 ──────────────────────────────
    if request.method == "GET":
        return render(request, "enter_receiver_info.html", {"order_number": order_number})

    if request.method != "POST":
        return HttpResponse("method error", status=405)

    # ── Step 1: 取出並驗證表單欄位 ──────────────────────
    try:
        receiver_name = request.POST.get("receiver_name", "").strip()
        receiver_phone = request.POST.get("receiver_phone", "").strip()
        receiver_address = request.POST.get("receiver_address", "").strip()
        pay_method = request.POST.get("pay_method", "").strip()
    except Exception as e:
        # request.POST 理論上不太會出錯,但保底攔一次,避免整頁 500
        logger.exception(f"[enter_receiver_info] 訂單 {order.order_number} 讀取表單欄位失敗")
        return render(request, "enter_receiver_info.html", {
            "order": order,
            "error": "表單資料讀取失敗,請重新填寫。",
        })

    if not receiver_name or not receiver_phone or not receiver_address:
        return render(request, "enter_receiver_info.html", {
            "order": order,
            "error": "收件人姓名、手機、地址皆為必填,請重新填寫。",
            "posted_name": receiver_name,
            "posted_phone": receiver_phone,
            "posted_address": receiver_address,
        })

    if pay_method not in ("ATM", "COD"):
        return render(request, "enter_receiver_info.html", {
            "order": order,
            "error": "請選擇付款方式。",
            "posted_name": receiver_name,
            "posted_phone": receiver_phone,
            "posted_address": receiver_address,
        })

    # ── Step 2: 存回 Order ──────────────────────────────
    try:
        order.receiver_name = receiver_name
        order.receiver_phone = receiver_phone
        order.receiver_address = receiver_address
        order.save()
    except Exception:
        logger.exception(f"[enter_receiver_info.save_order] 訂單 {order.order_number} 更新收件資訊失敗")
        return render(request, "enter_receiver_info.html", {
            "order": order,
            "error": "收件資訊儲存失敗,請稍後再試。",
            "posted_name": receiver_name,
            "posted_phone": receiver_phone,
            "posted_address": receiver_address,
        })

    # ── Step 3: 計算商品明細與金額 ───────────────────────
    try:
        items = order.items.select_related('product')
        item_names = "#".join([item.product.name for item in items])
        order_total = sum(item.price * item.quantity for item in items)
        shipping_fee = 60
        total_with_shipping = order_total + shipping_fee
    except Exception:
        logger.exception(f"[enter_receiver_info.calc_amount] 訂單 {order.order_number} 計算金額失敗")
        return render(request, "enter_receiver_info.html", {
            "order": order,
            "error": "計算訂單金額時發生錯誤,請稍後再試。",
        })

    # ── Step 4: 組 payload + 簽章 ─────────────────────────
    try:
        base_payload = {
            'merchant_id': "shop1234",
            'merchant_trade_no': order.order_number,
            'merchant_trade_date': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'user_id': request.user.id,
            'trade_amt': int(total_with_shipping),
            'trade_desc': order.remark or "購買商品",
            'item_name': item_names,
            'payment_type': "aio",
            'transaction_id': str(uuid.uuid4()),
            'status': order.status,
            'receiver_name': order.receiver_name,
            'receiver_address': order.receiver_address,
        }

        if pay_method == "ATM":
            payload = dict(base_payload)
            payload.update({
                'choose_payment': "ATM",
                'ReturnURL': f"{HF_SPACE_E_COMMERCE_URL}/commerce_shop/ecpay_mock_notify/",
                'PaymentInfoUrl': f"{HF_SPACE_E_COMMERCE_URL}/commerce_shop/payment_info/",
                'OrderResultURL': f"{HF_SPACE_E_COMMERCE_URL}/commerce_shop/payment_ok/",
                'action_url': f"{HF_SPACE_ECPAY_MOCK_URL}/gateway/ecpay_gateway_checkout/",
            })
        else:  # COD
            payload = dict(base_payload)
            payload.update({
                'choose_payment': "CVSCOD",
                'receiver_cell_phone': order.receiver_phone,
                'ReturnURL': f"{HF_SPACE_E_COMMERCE_URL}/commerce_shop/ecpay_mock_notify/",
                'OrderResultURL': f"{HF_SPACE_E_COMMERCE_URL}/commerce_shop/payment_ok/",
                'action_url': f"{HF_SPACE_ECPAY_MOCK_URL}/cod_gateway/cod_checkout/",
            })

        payload["check_mac_value"] = generate_check_mac_value(
            payload, ECPAY_HASH_KEY, ECPAY_HASH_IV
        )
    except Exception:
        logger.exception(f"[enter_receiver_info.build_payload] 訂單 {order.order_number} 組 payload/簽章失敗")
        return render(request, "enter_receiver_info.html", {
            "order": order,
            "error": "付款資料準備失敗,請稍後再試。",
        })

     # ── Step 5: 組自動送出表單的 HTML(呼叫共用函式,跟 ready_form 用同一份邏輯)──
    try:
        html = _build_auto_submit_html(payload)
    except Exception:
        logger.exception(f"[enter_receiver_info.build_html] 訂單 {order.order_number} 組自動送出頁失敗")
        return render(request, "enter_receiver_info.html", {
            "order": order,
            "error": "產生付款頁面失敗,請稍後再試。",
        })

    logger.info(f"[enter_receiver_info] 訂單 {order.order_number} 準備送出,"
                f"pay_method={pay_method}, action_url={payload['action_url']}")
    return HttpResponse(html)
    

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
#		  payment = Payment.objects.get(order=order)
		# 建立或更新 Payment 紀錄
		payment, created = Payment.objects.get_or_create(
			order=order,
			transaction_id=data["transaction_id"],
			defaults={
				"amount": data["trade_amt"],
				"payment_method": "ATM",
				"status": "success",
#				  "paid_at": datetime.datetime.strptime(paid_at, "%Y-%m-%d %H:%M:%S"),
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
			return redirect('home')	 # 或 redirect('cart_detail')
		cart_item.quantity = new_quantity
		cart_item.save()
		messages.success(request, f"{product.name} 已增加到購物車，數量：{cart_item.quantity}")
	else:
		if product.stock < 1:
			# 如果商品庫存為 0
			cart_item.delete()	# 刪除剛建立的項目
			messages.error(request, f"{product.name} 庫存不足，無法加入購物車")
		else:
			messages.success(request, f"{product.name} 已加入購物車，數量：{cart_item.quantity}")
	
	return redirect('cart_detail')
#	 return redirect('home')  # 或 redirect('cart_detail')


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
			"backend_url": BACKEND_URL
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
	每個 pending 訂單同時準備「ATM」與「COD(超商取貨付款)」兩份已簽章 payload,
	前端依使用者選擇的付款方式挑一份送出,避免前端臨時改欄位導致簽章對不上。
	"""
	try:
		user = request.user
		# 取得該使用者所有訂單，依照建立時間排序（最新的在前）
		orders = Order.objects.filter(user=user).order_by('-created_at')
		user_id = user.id
	except Exception as e:
#		 print(f"❌ [purchased_products.load_orders] {type(e).__name__}: {e}")
		logger.exception(f"❌ [purchased_products.load_orders] 讀取訂單失敗 {type(e).__name__}: {e}")  # 【修改】
		# 讀取訂單失敗時,寧可顯示空清單也不要整頁 500,讓使用者至少看得到頁面
		return render(request, 'purchased_products.html', {'order_list': [], 'load_error': str(e)})

	# 建立一個 list，把每個訂單和其商品（含小計）打包
	order_list = []

	for order in orders:
		# 取得該訂單的所有 OrderItem
		# 使用 select_related('product') 避免 N+1 查詢問題
		try:
			# 【修正】原本這段計算商品明細/運費/merchant_id 的邏輯遺失了,
			# 導致下面 base_payload 用到的 merchant_id、total_with_shipping、
			# item_names 等變數會是 NameError,這裡補回來
			items = order.items.select_related('product')
			item_names = "#".join([item.product.name for item in items])

			items_with_subtotal = []
			order_total = 0

			for item in items:
				subtotal = item.price * item.quantity
				items_with_subtotal.append({'item': item, 'subtotal': subtotal})
				order_total += subtotal

			shipping_fee = 60
			total_with_shipping = order_total + shipping_fee
			merchant_id = "shop1234"

			# 兩種付款方式共用的欄位
			base_payload = {
				'merchant_id': merchant_id,
				'merchant_trade_no': order.order_number,
				'merchant_trade_date': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
				'user_id': user_id,
				'trade_amt': int(total_with_shipping),
				'trade_desc': order.remark or "購買商品",
				'item_name': item_names,
				'payment_type': "aio",
				'transaction_id': str(uuid.uuid4()),
				'status': order.status,
				# Order model 本身就有 receiver_name(必填欄位),直接用即可,
				# 不用再去猜 user 身上的欄位
				'receiver_name': order.receiver_name,
			}

			# ---------- ATM 版 payload ----------
			atm_payload = dict(base_payload)
			atm_payload.update({
				'choose_payment': "ATM",
				'ReturnURL': f"{HF_SPACE_E_COMMERCE_URL}/commerce_shop/ecpay_mock_notify/",
				'PaymentInfoUrl': f"{HF_SPACE_E_COMMERCE_URL}/commerce_shop/payment_info/",
				'OrderResultURL': f"{HF_SPACE_E_COMMERCE_URL}/commerce_shop/payment_ok/",
				'action_url': f"{HF_SPACE_ECPAY_MOCK_URL}/gateway/ecpay_gateway_checkout/",
			})
			atm_payload["check_mac_value"] = generate_check_mac_value(
				atm_payload, ECPAY_HASH_KEY, ECPAY_HASH_IV
			)

			# ---------- COD 版 payload ----------
			# 取貨付款要通知的是「這筆訂單收件人」的手機,而不是帳號本身的手機
			# (兩者可能不同人,例如幫朋友代購),所以優先用 Order.receiver_phone。
			# 只有在 receiver_phone 意外是空值時,才 fallback 去 UserProfile 撈帳號手機備用。
			try:
				receiver_cell_phone = order.receiver_phone or ""
				if not receiver_cell_phone:
					receiver_cell_phone = user.userprofile.phone or ""
			except Exception as e:
				# UserProfile 可能不存在(OneToOneField 尚未建立),不影響主流程,
				# 只記錄一下方便追蹤,COD 欄位留空即可繼續往下走
#				 print(f"⚠️ [purchased_products.build_payload] 取得 userprofile.phone 失敗: " f"{type(e).__name__}: {e}")
				logger.exception(f"⚠️ [purchased_products.build_payload] 取得 userprofile.phone 失敗: " f"{type(e).__name__}: {e}")	# 【修改】
				receiver_cell_phone = ""

			cod_payload = dict(base_payload)
			cod_payload.update({
				'choose_payment': "CVSCOD",
				'receiver_cell_phone': receiver_cell_phone,
				'ReturnURL': f"{HF_SPACE_E_COMMERCE_URL}/commerce_shop/ecpay_mock_notify/",
				'OrderResultURL': f"{HF_SPACE_E_COMMERCE_URL}/commerce_shop/payment_ok/",
				'action_url': f"{HF_SPACE_ECPAY_MOCK_URL}/cod_gateway/cod_checkout/",
			})
			cod_payload["check_mac_value"] = generate_check_mac_value(
				cod_payload, ECPAY_HASH_KEY, ECPAY_HASH_IV
			)

			order_list.append({
				'order': order,
				'items': items_with_subtotal,
				'shipping_fee': shipping_fee,
				'total_with_shipping': total_with_shipping,
				'payment_payload_atm': json.dumps(atm_payload, ensure_ascii=False),
				'payment_payload_cod': json.dumps(cod_payload, ensure_ascii=False),
				'backend_url': BACKEND_URL,
			})
		except KeyError as e:
			# 某個訂單缺少必要欄位(例如 amount 是 None),記錄後跳過這筆,
			# 不要讓一筆壞資料拖垮整頁清單
#			 print(f"❌ [purchased_products.build_payload] 訂單 {order.order_number} 缺少欄位: {e}")
			logger.exception(f"❌ [purchased_products.build_payload] 訂單 {order.order_number} 缺少欄位")  # 【修改】
			continue
		except Exception as e:
#			 print(f"❌ [purchased_products.build_payload] 訂單 {order.order_number} 發生錯誤: "
			logger.exception(f"❌ [purchased_products.build_payload] 訂單 {order.order_number} 發生錯誤  {type(e).__name__}: {e}")  # 【修改】
			continue

	# 將整理好的訂單列表傳給模板
	return render(request, 'purchased_products.html', {'order_list': order_list})

def _build_auto_submit_html(payload: dict) -> str:
    """
    【重構】把「用 payload dict 組出自動送出的 HTML form」這段邏輯,
    從 ready_form 抽出來獨立成一個函式,讓 ready_form 和 enter_receiver_info
    都能重用同一份程式碼,不用維護兩份幾乎一樣的字串組裝邏輯。
    """
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
              action="{payload['action_url']}">
    """
    for key, value in payload.items():
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
    return html
	
# @require_POST
@login_required
def ready_form(request):
    """
    商城：接收 payment_payload,組成 HTML Form,自動 POST 到模擬綠界。
    【修改】組 HTML 的邏輯改成呼叫共用函式 _build_auto_submit_html(),
    ready_form 本身只負責「從 request.body 解析 JSON」這件事。
    """
    try:
        payment_payload = json.loads(request.body)
    except json.JSONDecodeError:
        logger.exception("[ready_form] request.body 不是合法 JSON")
        return HttpResponseBadRequest("JSON 格式錯誤")

    html = _build_auto_submit_html(payment_payload)
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
		"TransactionID": str(uuid.uuid4()),	 # 自動產生唯一交易編號
		"Status": order.status,
		# 🔑 綠界官方定義
		"ReturnURL": "http://127.0.0.1:8000/commerce_shop/ecpay_mock_notify/",	 # server-to-server callback, # 綠界回傳 URL
		"PaymentInfoUrl": "http://127.0.0.1:8000/commerce_shop/ready_form/",   # 綠界通知商城已取得虛擬帳號
		"OrderResultURL": "http://127.0.0.1:8000/commerce_shop/payment_ok/",  # browser redirect ,瀏覽器跳轉 URL
#			  "BankCode": bank_code,
#			  "vAccount": atm_account,
#			  "ExpireDate": expire_date,
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

	order = item.order	# 取得對應訂單

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
		merchant_trade_no = request.POST.get("MerchantTradeNo")	 # 商城訂單編號
		trade_no = request.POST.get("TradeNo")					 # 綠界交易編號
		trade_amt = request.POST.get("TradeAmt")				 # 交易金額
		payment_date = request.POST.get("PaymentDate")			 # 付款完成時間
		payment_type = request.POST.get("PaymentType")			 # 付款方式
		rtn_code = request.POST.get("RtnCode")					 # 回傳代碼 (1=成功)
		rtn_msg = request.POST.get("RtnMsg")					 # 回傳訊息

		try:
			# 找到商城的訂單
			order = Order.objects.get(order_number=merchant_trade_no)
		except Order.DoesNotExist:
			return HttpResponse("0|Order Not Found")

		# 更新訂單狀態
		if rtn_code == "1":	 # 成功
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
#		  return HttpResponse("method error")

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
	trade_no = payment_payload.get("trade_no")					# 交易編號
	trade_amt = payment_payload.get("trade_amt")				 # 交易金額
	paid_at = payment_payload.get("order_pay_at")			# 付款完成時間
	payment_method = payment_payload.get("choose_payment")			 # 付款方式
	
	   
	try:
		# 找到商城的訂單
		order = Order.objects.get(order_number=merchant_trade_no)
#		  orders = Order.objects.filter(order_number=merchant_trade_no).order_by("-created_at")
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
#	  if not created:
#		  # 如果已存在，更新狀態
#		  payment.status = "success"
#		  payment.paid_at = datetime.datetime.strptime(payment_date, "%Y-%m-%d %H:%M:%S")
#		  payment.response_data = dict(request.POST)
#		  payment.save()
	# 返回首頁
#	  return redirect('home')

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
#		  order_items = order.items.select_related('product')

		# 把每個商品名稱串起來 (綠界格式通常是 "商品A#商品B#商品C")
		item_names = "#".join([item.product.name for item in items])

		# 建立一個 list 來存每個商品和它的小計
		items_with_subtotal = []
		order_total = 0	 # 先建立訂單小計（未加運費）,移到迴圈外,避免每次重設

		for item in items:
			# 計算每個商品小計：單價 × 數量
			subtotal = item.price * item.quantity
#			 order_total = 0  # 先建立訂單小計（未加運費）

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
			'merchant_trade_date': merchant_trade_date,	 # 訂單日期 
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
			'ReturnURL': "http://127.0.0.1:8000/commerce_shop/ecpay_mock_notify/",	 # server-to-server callback, # 綠界回傳 URL
			'PaymentInfoUrl': "http://127.0.0.1:8000/commerce_shop/payment_info/",	 # 綠界通知商城已取得虛擬帳號
			'OrderResultURL': "http://127.0.0.1:8000/commerce_shop/payment_ok/",  # browser redirect ,瀏覽器跳轉 URL
			'action_url': "http://127.0.0.1:8001/gateway/ecpay_gateway_checkout/",
#			  "BankCode": bank_code,
#			  "vAccount": atm_account,
#			  "ExpireDate": expire_date,
		}
		payment_payload["check_mac_value"] = generate_check_mac_value(payment_payload,ECPAY_HASH_KEY,ECPAY_HASH_IV)

		payment_payload = json.dumps(payment_payload, ensure_ascii=False)
		
		# 將訂單和其商品列表加入 order_list
		order_list.append({
			'order': order,
			'items': items_with_subtotal,
			'shipping_fee': shipping_fee,			# 運費
			'total_with_shipping': total_with_shipping,	 # 含運費總額
			'payment_payload': payment_payload,	  # ✅ 新增這個 dict
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
#	  if hasattr(order, 'payment'):
#		  messages.warning(request, "此訂單已建立付款")
#		  return redirect('purchased_products')
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
#		  payment = Payment.objects.get(transaction_id=transaction_id)
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
