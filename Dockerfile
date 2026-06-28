FROM python:3.14-slim

# 設定環境變數:不產生.pyc檔案,且log及時輸出方便在HF Logs查看
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 建立並切換到非 ROOT 使用者(Hugging Face Spaces 規定,UID 1000)
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \ PATH=/home/user/.local/bin:$PATH

WORKDIR $HOME/app

#WORKDIR /app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \ 
    pip install --no-cache-dir -r requirements.txt

COPY --chown=user . .

# 執行靜態檔案收集(這會把 BS5 的 CSS/JS 整理到 staticfiles 資料夾)
RUN python manage.py collectstatic --noinput

# 開放 Port 7860 (Hugging Face 規定)
EXPOSE 7860

# 啟動指定
#CMD sh -c "python manage.py migrate && gunicorn E_commerce.wsgi:application --bind 0.0.0.0:7860"
CMD ["gunicorn", \
     "--bind", "0.0.0.0:7860", \
	 "--workers", "4", \
	 "--timeout", "120", \
	 "--access-logfile", "-", \
	 "E_commerce.wsgi:application"]