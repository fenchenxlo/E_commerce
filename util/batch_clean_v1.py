import pandas as pd
import re
import os

# === 設定資料夾路徑 ===
input_folder = r"C:\Users\fenchen_lo\Downloads\下載檔案區"      # 放原始檔案
output_folder = r"C:\Users\fenchen_lo\Downloads\輸出檔案區"    # 清理後輸出

# 若 output 資料夾不存在就建立
os.makedirs(output_folder, exist_ok=True)

# === 清理函式 ===
def clean_p(value):
    if pd.isna(value):
        return value

    # 不處理純數字
    if isinstance(value, (int, float)):
        if value == 0:
            return "N/A"
        return value  

    if str(value).isdigit():
        if value == "0":
            return "N/A"
        return int(value)

    text = str(value)

    # 1. 移除 \n 及其後內容
    text = text.split("\n")[0]

    # 2. 移除 $
    text = text.replace("$", "")

    # 3. 移除 ,
    text = text.replace(",", "")

    # 4 & 5. 移除數字 0 與字串 "0"
#     text = text.replace("0", "")

    # 7. 移除 price（不分大小寫）
    text = re.sub(r"price", "", text, flags=re.IGNORECASE)

#     # 6A + 6B：移除含字母的字串，但保留純數字
#     # 移除含字母的字串（含字母即可）
#     text = re.sub(r"\b(?=.*[A-Za-z])[A-Za-z0-9]+\b", "", text)

    #✔ 移除所有含字母的字串（保留純數字）
    text = re.sub(r"\b\w*[A-Za-z]\w*\b", "", text)

    # 一次移除所有類似'的字元
    text = re.sub(r"[\'’‘＇]", "", text)
    
    # 去除多餘空白
    text = text.strip()
    
    if text.isdigit():
        text = int(text)
    else:
        text = "N/A" # 或 return text，看你需求
    
    return text


# === 批次處理 ===
for filename in os.listdir(input_folder):
    filepath = os.path.join(input_folder, filename)

    # 處理 Excel
    if filename.lower().endswith(".xlsx"):
        df = pd.read_excel(filepath)

    # 處理 JSON
    elif filename.lower().endswith(".json"):
        df = pd.read_json(filepath)

    else:
        print(f"跳過非資料檔案：{filename}")
        continue

    # 若沒有 p 欄位就跳過
    if "price" not in df.columns:
        print(f"檔案 {filename} 沒有 p 欄位，已跳過")
        continue
    
    # ⭐ 保留原始排序
    df["_original_order"] = df.index
    df["price"] = df["price"].apply(clean_p)

    df = (
        df
        .sort_values("_original_order", kind="stable")
        .drop(columns="_original_order")
    )
    
    # 套用清理
#     df["price"] = df["price"].apply(clean_p)
    
    # ⭐ 恢復原始排序
#     df = df.sort_values("_original_order").drop(columns=["_original_order"])

    # 輸出檔案
    output_path = os.path.join(output_folder, filename)
    
     # 解除唯讀屬性（如果檔案已經存在）
    if os.path.exists(output_path):
        os.chmod(output_path, stat.S_IWRITE)

    if filename.lower().endswith(".xlsx"):
        df.to_excel(output_path, index=False)
    else:
        df.to_json(output_path, orient="records", force_ascii=False)

    print(f"已處理：{filename} → {output_path}")

print("批次處理完成！")