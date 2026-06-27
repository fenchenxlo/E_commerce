# 好的，以下是用 Python 實現的範例程式碼，這段程式會讀取指定資料夾中的所有 `.xlsx` 檔案，並將它們合併成一個單一的檔案（可以是 `.xlsx` 或 `.json` 格式）。這裡會使用 `pandas` 庫來處理 Excel 和 JSON 格式的讀取與寫入。
# 
# ### 安裝必要的庫：
# 
# 首先，請確保你已經安裝了 `pandas` 和 `openpyxl`（處理 Excel 檔案）：
# 
# ```bash
# pip install pandas openpyxl
# ```
# 
# ### 合併 `.xlsx` 檔案並輸出為 `.xlsx` 或 `.json` 檔案
# 
# 這段程式會讀取資料夾中的所有 `.xlsx` 檔案，並將它們合併成一個 DataFrame，然後輸出為新的 `.xlsx` 或 `.json` 檔案。

### Python 程式碼：

# ```python
import os
import pandas as pd

# 讀取指定資料夾中的所有xlsx檔案，並合併成一個檔案
def merge_excel_files(input_folder, output_file, output_format='xlsx'):
    # 用來儲存所有合併後的資料
    all_data = []

    # 遍歷資料夾，找出所有的 .xlsx 檔案
    for file_name in os.listdir(input_folder):
        if file_name.endswith('.xlsx'):  # 只處理 .xlsx 檔案
            file_path = os.path.join(input_folder, file_name)
            print(f"讀取檔案: {file_path}")

            # 讀取 Excel 檔案
            df = pd.read_excel(file_path)

            # 將讀取的資料加入 all_data 列表
            all_data.append(df)

    # 將所有資料合併成一個 DataFrame
    combined_df = pd.concat(all_data, ignore_index=True)

    # 根據使用者需求，輸出為 .xlsx 或 .json 檔案
    if output_format == 'xlsx':
        # 輸出為 Excel 檔案
        combined_df.to_excel(output_file, index=False)
        print(f"合併完成，檔案已儲存為 {output_file}")
    elif output_format == 'json':
        # 輸出為 JSON 檔案
        combined_df.to_json(output_file, orient='records', lines=True)
        print(f"合併完成，檔案已儲存為 {output_file}")

# 使用範例：
input_folder = 'path/to/your/folder'  # 替換為你的資料夾路徑
output_file = 'merged_data.xlsx'  # 輸出的檔案名稱，可以改成 .json 格式

# 合併並輸出為 Excel 檔案
merge_excel_files(input_folder, output_file, output_format='xlsx')

# 如果你想輸出為 JSON 檔案，可以使用：
# merge_excel_files(input_folder, 'merged_data.json', output_format='json')
```

### 程式說明：

# 1. **`merge_excel_files`** 函數：
# 
#    * `input_folder`：是資料夾的路徑，裡面存放著 `.xlsx` 檔案。
#    * `output_file`：合併後儲存的檔案名稱，可以是 `.xlsx` 或 `.json` 格式。
#    * `output_format`：這個參數決定了輸出的格式，可以是 `'xlsx'` 或 `'json'`。
# 
# 2. **資料合併**：
# 
#    * 程式會遍歷指定資料夾中的所有 `.xlsx` 檔案，並用 `pandas` 讀取每個檔案的資料，將它們合併成一個大的 DataFrame。
#    * 使用 `pd.concat()` 函數將每個檔案的 DataFrame 合併到一起，這樣可以確保所有的資料都會合併在一個表格裡。
# 
# 3. **輸出**：
# 
#    * 如果 `output_format` 是 `'xlsx'`，程式會將合併後的資料儲存為 `.xlsx` 檔案。
#    * 如果 `output_format` 是 `'json'`，程式會將合併後的資料儲存為 `.json` 檔案，並使用 `orient='records'` 和 `lines=True` 來將每一列資料當作 JSON 物件寫入檔案。
# 
# ### 範例使用：
# 
# * 假設你有一個資料夾 `data_folder/`，裡面包含多個 `.xlsx` 檔案，執行 `merge_excel_files('data_folder', 'merged_data.xlsx')` 會將所有 Excel 檔案合併並輸出為 `merged_data.xlsx`。
# * 如果你想輸出為 `.json`，只需要修改 `output_format='json'` 並指定 `.json` 檔案名稱。
# 
# ### 注意事項：
# 
# * 確保資料夾中的每個 `.xlsx` 檔案結構相同（例如有相同的欄位名稱），否則合併時可能會出現錯誤。
# * 如果某些檔案資料欄位不一致，`pandas` 會將缺失的欄位填入 `NaN`。
# 
# 希望這段程式能幫助你順利完成資料合併的工作！如果有任何問題或進一步的需求，隨時告訴我！
