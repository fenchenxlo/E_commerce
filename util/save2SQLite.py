import pandas as pd
import sqlite3
from pathlib import Path
import re

# xlsx寫入SQLite DB
class XlsxToSQLite:
    def __init__(self, xlsx_path: str, db_path: str = "products.db"):
        self.xlsx_path = Path(xlsx_path)
        self.db_path = Path(db_path)
        self.table_name = "products" # DB的table name

    # 1️⃣ 讀取 Excel
    def load_xlsx(self) -> pd.DataFrame:
        return pd.read_excel(
            self.xlsx_path, engine='openpyxl',
            keep_default_na=False
        )
#         print(f"讀取檔案: {self.xlsx_path}")

    # 2️⃣ 判斷 source (平台來源)
    def infer_source(self, row) -> str:
        url = str(row.get("url", "")).lower()
        bu = str(row.get("BU", "")).lower()
        pid = str(row.get("Id", ""))
        isPChome = str(row.get("isPChome", ""))
        
        # 1. url 欄位準確率高
        if "pchome" in url:
            return "pchome"
        if "yahoo" in url:
            return "yahoo"

        # 2. BU 欄位
        if bu == "ec":
            return "pchome"

        # 3. Id (欄位)pattern（PChome）
        if re.match(r"^[A-Z0-9]{5,}-\d+[A-Z0-9]+$", pid):
            return "pchome"

        # 4. couponActid 欄位
        coupon = row.get("couponActid")
        if pd.notna(coupon) and str(coupon) not in ("[]", "nan", ""):
            return "pchome"
        
        # 5. isPChome 欄位
        if isPChome == '':
            return "yahoo"
        
        return "unknown"

    # 3️⃣ 清理 / 正規化 dataframe
    def clean_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        df.columns = [c.strip() for c in df.columns]

        # 自動填 source（覆蓋原本空值）
        df["source"] = df.apply(self.infer_source, axis=1)

        # couponActid
        if "couponActid" in df.columns:
            df["couponActid"] = df["couponActid"].astype(str)  # 轉文字

        # 價格
        for col in ["price", "originPrice"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")  # 轉數字

        # review_count(回應數)
        if "review_count" in df.columns:
            df["review_count"] = pd.to_numeric(  # 轉數字
                df["review_count"], errors="coerce"
            )

        return df

    # 4️⃣ 建表
    def create_table(self):
        conn = sqlite3.connect(self.db_path)  # 取得sqlite連線
        cursor = conn.cursor()  # 取得cursor

        cursor.execute(  # cursor執行 SQL語法
            f"""
            CREATE TABLE IF NOT EXISTS {self.table_name} (
                id TEXT,
                cateId TEXT,
                picS TEXT,
                picB TEXT,
                name TEXT,
                regex_name TEXT,
                describe TEXT,
                price INTEGER,
                originPrice INTEGER,
                author TEXT,
                brand TEXT,
                publishDate TEXT,
                isPChome INTEGER,
                isNC17 INTEGER,
                couponActid TEXT,
                BU TEXT,
                source TEXT,
                time TEXT,
                url TEXT,
                rating TEXT,
                review_count INTEGER,
                sales TEXT
            )
            """
        )

        conn.commit()  # 儲存 cursor執行 建表SQL語法
        conn.close()  # 連線關閉

    # 5️⃣ 寫入 SQLite
    def insert_to_sqlite(self, df: pd.DataFrame, if_exists="append"):
        conn = sqlite3.connect(self.db_path)  # 取得sqlite連線
        df.to_sql(self.table_name, conn, if_exists=if_exists, index=False)  # 把df資料寫入SQLite DB
        conn.close()  # 連線關閉

    # 6️⃣ 一鍵執行
    def run(self, if_exists="append"):
        df = self.load_xlsx()  # 讀取 Excel
        
        df = self.clean_dataframe(df)  # 清理 / 正規化 dataframe
        
        self.create_table()  # 建表
        
        self.insert_to_sqlite(df, if_exists=if_exists)  #寫入 SQLite

# if __name__ == "__main__":
#     xlsxPath = r"C:\Users\USER\Downloads\輸出iphone17檔案區\output_iphone17_with_regex_name.xlsx"
#     dbPath = r"C:\Users\USER\AppData\LocalLow\DefaultCompany\mary\lkk-成果發表\products.db"
#     
#     loader = XlsxToSQLite(
#         xlsx_path=xlsxPath,
#         db_path=dbPath
#     )
#     
#     loader.run(if_exists="append")
#     
#     print('寫入SQLite 完成~')
    
