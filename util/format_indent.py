import argparse
import os

def fix_indentation(file_path):
    if not os.path.exists(file_path):
        print(f"❌ 錯誤：找不到該檔案 -> {file_path}")
        return

    # 1. 讀取原始檔案內容
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except UnicodeDecodeError:
        # 如果不是 UTF-8 格式，則嘗試使用 Windows 常見的 cp950 讀取
        with open(file_path, 'r', encoding='cp950', errors='ignore') as f:
            lines = f.readlines()

    new_lines = []
    
    # 2. 逐行安全處理
    for line in lines:
        # 分離行首的空白/Tab 與實際的程式碼內容
        stripped = line.lstrip('\t ')
        indent = line[:len(line) - len(stripped)]
        
        # 僅將「行首縮進區域」中的 Tab 替換為 4 個空格
        # 這能確保程式碼內部的字串內容（如 text = "hello\tworld"）絕對不會被破壞
        new_indent = indent.replace('\t', '    ') 
        
        new_lines.append(new_indent + stripped)

    # 3. 將修正後的內容覆蓋回原檔案
    with open(file_path, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
        
    print(f"✨ 順利完成縮進標準化：{os.path.basename(file_path)}")

if __name__ == "__main__":
    # 設定參數解析器，方便在終端機直接傳入檔案路徑
    parser = argparse.ArgumentParser(description="安全地將行首 Tab 轉換為 4 個空格。")
    parser.add_argument("file", help="要處理的 .py 檔案路徑")
    args = parser.parse_args()
    
    fix_indentation(args.file)
