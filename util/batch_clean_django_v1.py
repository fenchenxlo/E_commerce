import pandas as pd
import re,stat
import os

class batchColClean_django:
    """批次清理欄位類別"""
    def __init__(self,keyWord,inputFolder,outputFolder):       
        # === 設定資料夾路徑 ===
        self.input_folder = inputFolder      # 放原始檔案
        self.output_folder = outputFolder    # 清理後輸出
        self.keyWord = keyWord
        # 若 output 資料夾不存在就建立
        os.makedirs(self.output_folder, exist_ok=True)

    # === 清理函式 ===
    def clean_price(self,value):
        if pd.isna(value):  # value如果是N/A
            return value

        # 不處理純數字
        if isinstance(value, (int, float)):  # value如果是int或float
            if value == 0:
                return "N/A"
            return value  

        if str(value).isdigit():  # 轉成文字的value如果是數字
            if value == "0":
                return "N/A"
            return int(value)  # 將value轉成int

        text = str(value)  # 將value轉成str

        # 從text中移除所有「包含英文或中文字的單字」，只留下純數字、符號等內容。
        text = re.sub(
            r'\b\w*[A-Za-z\u4e00-\u9fff]\w*\b',
            '',
            text
        )
        
        # 移除 \n 及其後內容
        text = text.split("\n")[0]  # 將text用split("\n")切成2半,取第0項

        # 移除 $
        text = text.replace("$", "")  # 將text用replace "$"轉成""

        # 移除 ,
        text = text.replace(",", "")  # 將text用replace ","轉成""

        # 移除 price（不分大小寫）
        text = re.sub(r"price", "", text, flags=re.IGNORECASE)

        # 清空多餘空白
        text = re.sub(r'\s+', ' ', text).strip()

        # 若沒有任何數字，統一回傳 N/A
        if not re.search(r'\d', text):
            return 'N/A'

        # 一次移除所有類似'的字元
        text = re.sub(r"[\'’‘＇]", "", text)
        
        if text.isdigit():  # 如果text是文字型態的數字
            text = int(text)  # 將value轉成int
        else:
            text = "N/A" 
        
        return text

    def clean_url(self,x):
        return str(x).strip("()',")  # 將strip()內的符號,取代為''

    def clean_rating(self,value):
#         print(f"value typt({type(value)},value = {value})")
        try:
            # 處理可轉成float or int
            if isinstance(float(value), (int, float)):  # value如果是int或float
                return float(value)
            if isinstance(int(value), (int, float)):  # value如果是int或float
                return float(value)
#                 print(type(value))
            return value
        except ValueError:
            if value == "無評分" or value == "無評價" or value == "":
#                 print("字串")
                value = 0
            return value      

        # 清空多餘空白
        value = re.sub(r'\s+', ' ', value).strip()
        
        return float(value)  # 將value轉成float

    def clean_review_count(self,value):
        if value is None or value == '':  # value如果是None或''
            return 0
        # 處理可轉成int
        if isinstance(int(value), (int, float)):  # value如果是int或float
            return value            
#         if value.isdigit():  # 如果value是文字型態的數字
#             value = int(value)  # 將value轉成int
        
        return value
    
    def clean_sales(self,value):
        if value is None or value == '':  # value如果是None或''
            return 0
#         if not isinstance(int(value), (int, float)):  # value如果不是int或float
#             return 0
        
        if value.isdigit():  # 如果value是文字型態的數字
            return int(value)  # 將value轉成int
               
        # 移除無銷量資訊
        value = value.replace("無銷量資訊", "0")  # 將value用replace ","轉成None
        # 移除銷量資訊
        value = value.replace("總銷量", "")  # 將value用replace ","轉成""
        # 一次移除所有類似>的字元
        value = re.sub(r"[>]", "", value)

        # 清空多餘空白
        value = re.sub(r'\s+', ' ', value).strip()
        
        if value.isdigit():  # 如果value是文字型態的數字
            value = int(value)  # 將value轉成int
        
        return value
    
    # === 批次處理 ===
    def batchClean(self):        
        for filename in os.listdir(self.input_folder):  #如果filename在os.listdir()的清單內
            filepath = os.path.join(self.input_folder, filename)
            
            if self.keyWord in filename:
                # 處理 Excel
                if filename.lower().endswith(".xlsx"):  # 將filename結尾是".xlsx"的filename轉成小寫
                    # 讀取 Excel 檔案
                    df = pd.read_excel(
                        filepath,
                        keep_default_na=False  # 設為False "N/A"就會保留
                    )                               
                
                # ⭐ 保留原始排序            
                # 在所有清理、過濾、合併之前，先加這一行
                df = df.assign(_orig_idx=range(len(df)))
                        
                
                # 若有 rating 欄位就處理
                if "rating" in df.columns:
                    df["rating"] = df["rating"].apply(self.clean_rating)  # .apply去執行()內的方法self.clean_rating
                
                # 若有 review_count 欄位就處理
                if "review_count" in df.columns:
                    df["review_count"] = df["review_count"].apply(self.clean_review_count)  # .apply去執行()內的方法self.clean_review_count                
                
                df["sales"] = df["sales"].apply(self.clean_sales)  # .apply去執行()內的方法self.clean_sales
                
                # 最後想回到最原始的順序時：
                df = df.sort_values("_orig_idx").drop(columns="_orig_idx")

                # 輸出檔案
                output_path = os.path.join(self.output_folder, filename)
                
                 # 解除唯讀屬性（如果檔案已經存在）
                if os.path.exists(output_path):
                    os.chmod(output_path, stat.S_IWRITE)

                if filename.lower().endswith(".xlsx"):
                    df.to_excel(output_path, index=False)  # 將 df資料轉存成excel檔

                print(f"已處理：{filename} → {output_path}")

        print("批次處理完成！")
