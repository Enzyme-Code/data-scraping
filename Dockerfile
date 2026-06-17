# 採用官方輕量版 Python 環境（Debian 系統）
FROM python:3.10-slim

# 設定容器內的工作目錄為 /app
WORKDIR /app

# 複製套件清單並安裝
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製你本地所有的程式碼進去容器
COPY . .

# CLI 模組端點
CMD ["python", "-m", "domain.cli.weather"]