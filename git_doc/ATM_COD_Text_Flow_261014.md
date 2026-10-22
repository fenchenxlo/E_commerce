# ATM / COD 文字版流程（2026-10-14 更新版）

> 依 `E-Shop_Api_1012.zip` 最新 code 修訂。`E`=E_commerce、`P`=ecpay_mock、`B`=Bank_site。
> **相較舊版的修改**：①ATM 未收到款項時 Order 維持 pending_payment、不釋放庫存（舊版寫成 failed 是錯的）；②新增 ATM cancelled 守衛；③新增刪除訂單/品項與取消同步、金額重算。

## 一、ATM 虛擬帳號流程

### 1. 建立訂單與取得虛擬帳號
```
[買家瀏覽器]
  │ 購物車 → 結帳
  ▼
E  POST /api/checkout
  │ ① 建立 Order(pending_payment)、OrderItem
  │ ② 預留庫存：Product.stock↓、reserved_stock↑、InventoryReservation=reserved
  ▼
E  purchased_products（訂單頁，顯示「待處理 / 尚未建立交易」）
  │ 點「前往填寫收件資訊並付款」
  ▼
E  enter_receiver_info → 填收件資料、選 ATM
  │ POST /api/checkout（第二次，帶 order_number）
  ▼
E  OrderService（更新收件資訊、payment_method=ATM）
  ▼
E  PaymentService → ECPayMockAdapter（簽 CheckMacValue，httpx）
  │ 送 merchant_trade_no(=order_number)、trade_amt、user_id、receiver_name…
  ▼
P  /gateway/ecpay_gateway_checkout/
  │ ③ 驗 CheckMacValue
  │ ④ 建立 gateway.Order（_ensure_gateway_order）
  │ ⑤ 先 httpx 呼叫 Bank（下游），成功後才寫自己 DB
  ▼
B  /notify/create_account/
  │ ⑥ 驗 CheckMacValue
  │ ⑦ 建立 VirtualAccount(status=atm_created)
  │    產生 bank_code=013、v_account、expire_date（3 天）
  ▼ 回傳 bank_code / v_account / expire_date
P  ⑧ 建立 PaymentRequest(atm_created)，記錄虛擬帳號
  │ ⑨ httpx 通知 E
  ▼
E  /commerce_shop/atm_payment_notify/
  │ ⑩ 驗 CheckMacValue
  │ ⑪ PaymentService.handle_atm_callback：建立 Payment(pending)，
  │    存 bank_code / v_account / expire_date
  │    Order 仍是 pending_payment
  ▼
[買家] 訂單頁顯示：訂單狀態「待處理」、交易狀態「待付款」＋ ATM 資訊
```

### 2. 模擬頁（Bank_site 後台）
每個動作的順序都一樣：**下游先成功，才寫自己的 DB**，避免三邊不一致。

```
■ 模擬收到款項 simulate_paid/<no>/
B  檢查：已 paid 不可重複；已 cancelled 不可模擬
  │ 先通知下游
  ▼
P  /gateway/payment_notify/（驗 MAC）→ ECPayService.process_payment_notification
  │ 先通知 E
  ▼
E  atm_payment_notify → Payment=success，Order=paid，庫存 commit
  │ （逾期單被改 paid：先 _re_reserve_inventory 再 commit）
  ▲ 成功回傳
P  PaymentRequest=atm_paid，gateway.Order=paid
  ▲
B  最後才寫 VirtualAccount=paid

■ 模擬未收到款項 simulate_failed/<no>/
B → P(atm_failed) → E：Payment=failed，**Order 維持 pending_payment，不釋放庫存**（可再取消或重付）
  （若該單原為 paid：走 _recommit_to_reserved，把已 commit 的庫存退回預留）
P  PaymentRequest=atm_failed，gateway.Order=failed（P、B 的 failed 只是自己的狀態，不代表 E 的 Order=failed）
B  VirtualAccount=unpaid
（已 paid 的帳號仍可再模擬 failed，這是你原本的設計）

■ 模擬逾期未付款 simulate_expired/<no>/
B  已 expired 不可重送；已 cancelled 不可模擬
B → P(atm_expired) → E：Payment=expired，Order=expired，釋放庫存（已出貨 shipped 的單不可逾期）
P  PaymentRequest=atm_expired，gateway.Order=expired
B  VirtualAccount=expired
（E 的 expired 是終態：只有模擬頁可以改回其他狀態，
  改回時會 _re_reserve_inventory，庫存不足就整筆回滾）
```

### 3. 取消訂單（新功能，方向相反：從商城往下游）
```
[買家] 訂單頁按「取消訂單」（Order 為 pending_payment 或 failed 才有按鈕）
  ▼
E  cancel_order 視圖 → PaymentService.cancel_order
  │ 檢查狀態；找最新 ATM Payment(pending/failed)
  │ 先通知下游
  ▼
P  /gateway/cancel_order/（驗 MAC）→ ECPayService.cancel_order
  │ 擋：PaymentRequest 為 atm_paid / atm_expired
  │ 先通知下游
  ▼
B  /notify/cancel_account/<no>/（驗 MAC）
  │ 擋：VirtualAccount 為 paid / expired
  │ VirtualAccount=cancelled（Bank 是鏈尾，直接寫）
  ▲ 成功
P  PaymentRequest=atm_cancelled，gateway.Order=cancelled
  ▲ 成功
E  Order=cancelled、最新 Payment=cancelled、釋放庫存
  （任何一層失敗：本層不寫 DB，錯誤原因回到訂單頁顯示）
```

### 4. ATM 狀態對照
| 事件 | E Order | E Payment | P PaymentRequest | B VirtualAccount |
|---|---|---|---|---|
| 建立帳號 | pending_payment | pending | atm_created | atm_created |
| 已付款 | paid | success | atm_paid | paid |
| 未收到款項 | pending_payment（不變） | failed | atm_failed | unpaid |
| 逾期 | expired | expired | atm_expired | expired |
| 取消 | cancelled | cancelled | atm_cancelled | cancelled |

### 3-1. 【新增】已取消訂單的 ATM 防線
```
Bank 模擬頁、P 的通知、E 的 handle_atm_callback 三層都擋 cancelled：
E  if order.status == "cancelled": raise ValueError("訂單已取消，無法更新 ATM 付款狀態")
```

### 3-2. 【新增】刪除訂單 / 刪除品項（與取消同步）
```
■ 刪除整張訂單 delete_order（POST）
E  先 PaymentService.cancel_order(order)  ← 走 3. 的 E→P→B 取消鏈
  │ 失敗 → 提示「刪除失敗，無法同步取消付款資訊」，不刪
  │ 成功（或本來就是 cancelled、無付款資訊）→ 才刪除訂單

■ 刪除品項 delete_order_item
E  擋：shipped / paid / expired；或「已有付款資訊且未取消」→ 提示「請先按取消訂單」
  │ 未取消訂單：stock+、reserved_stock−、預留標 released
  │ 已取消訂單：不動庫存（取消時已釋放）
  │ 還有剩餘品項 → 重算 total_amount = 品項小計 + 運費 60
  │ 品項刪光 → 刪除整張訂單
■ 訂單頁按鈕：已取消、或（待處理/付款失敗且無付款資訊）才有刪除鈕；其餘顯示「請先取消訂單」
```

## 二、COD 超商取貨付款流程

COD **不經過 Bank_site**，只有 E 與 P 兩方。

### 1. 選門市與建立 COD 訂單
```
[買家] E enter_receiver_info → 選 COD
  │ POST /api/checkout（訂單已是 pending_payment，庫存已預留）
  ▼
E  將買家導向 P（簽好 CheckMacValue 的表單，由瀏覽器送出）
  ▼
P  /cod_gateway/cod_checkout/
  │ ① 驗 CheckMacValue（hmac.compare_digest）
  │ ② CODService.prepare_checkout：只驗欄位，不寫 DB
  ▼
P  select_store（Leaflet + taiwan.mbtiles 地圖，選 7-11 / 全家 / 萊爾富 / OK）
  ▼
P  review_store（確認門市資料）
  ▼
P  /cod_gateway/confirm_store/ → CODService.confirm_store
  │ ③ 先 httpx 通知 E（下游）
  ▼
E  /commerce_shop/cod_store_confirmed/ 與 cod_payment_notify
  │ ④ 驗 MAC；把門市資訊存在 COD Payment（不是 Order）
  │ ⑤ Payment=pending，Order 維持 pending_payment
  ▲ 成功
P  ⑥ 建立 gateway.Order + CODPaymentRequest(cod_created)，
  │    記錄 store_id / name / address / lat / lng
  ▼
[買家] 回訂單頁：「待處理」、交易狀態「待付款」，並顯示取貨門市
```

### 2. 模擬頁（ecpay_mock `query_and_simulate_cod`）
```
■ 共通規則（CODService.simulate）
P  找不到 COD 紀錄 → 錯誤；未選門市 → 錯誤；已 cancelled → 拒絕
P  ① 先 httpx 通知 E，payload 帶 simulate="1"（簽進 CheckMacValue）
E  handle_cod_callback：只有帶 simulate 標記才允許改動 expired 的單
P  ② E 成功後才寫 CODPaymentRequest 與 gateway.Order

■ 各動作
  貨品已送達超商 mock_shipped   → cod_shipped → E Order=shipped
  已取貨付款     simulate_paid  → cod_paid    → E Payment=success，Order=paid，庫存 commit
  取貨付款失敗   simulate_failed→ cod_failed  → E Payment=failed，Order 仍 pending_payment
  逾期未付款     simulate_expired→cod_expired → E Payment/Order=expired，釋放庫存
  貨品未送達     mock_created   → cod_created → E Order=pending_payment
```

### 3. 取消訂單（COD）
```
[買家] 訂單頁按「取消訂單」
  ▼
E  PaymentService.cancel_order（Order 須為 pending_payment / failed）
  │ 先通知下游
  ▼
P  /cod_gateway/cod_cancel/（驗 MAC）→ CODService.cancel
  │ 在鎖內判斷：
  │   cod_created、cod_failed → 可取消
  │   cod_shipped、cod_paid、cod_expired → 拒絕，回原因
  │   找不到 COD 紀錄（尚未選門市）→ 視為成功，沒東西需取消
  │ CODPaymentRequest=cod_cancelled，gateway.Order=cancelled（P 是鏈尾，直接寫）
  ▲ 成功
E  Order=cancelled、Payment=cancelled、釋放庫存
```

### 4. COD 狀態對照
| P 的 COD 狀態 | 中文 | E Order | E Payment | 能取消？ |
|---|---|---|---|---|
| cod_created | 待出貨 | pending_payment | pending | 可以 |
| cod_shipped | 配送中,待取貨付款 | shipped | pending | 不行 |
| cod_paid | 已取貨付款 | paid | success | 不行 |
| cod_failed | 取貨付款失敗 | pending_payment | failed | 可以 |
| cod_expired | 逾期未付款 | expired | expired | 不行 |
| cod_cancelled | 訂單已取消 | cancelled | cancelled | 已完成 |

## 三、兩種流程的共同規則
- **簽章**：每一段 server-to-server 都送 CheckMacValue，收的一方先驗證才處理。
- **寫入順序**：先呼叫下游，下游成功才寫自己的 DB。鏈尾（ATM 的 Bank、COD 的 ecpay_mock）直接寫。
- **庫存**：結帳時預留（reserved）；付款成功時 commit；失敗、逾期、取消時釋放（released）。
- **終態保護**：`expired` 只有模擬頁帶標記才能改，其他入口一律拒絕。
- **兩條路方向不同**：付款類事件由下往上（B → P → E），取消由上往下（E → P → B）。
- **取消後鎖死**：cancelled 為終態，ATM / COD 的模擬與回呼都會被拒絕。
