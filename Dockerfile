FROM python:3.9

# تثبيت متطلبات نظام التشغيل للمتصفحات
RUN apt-get update && apt-get install -y \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxext6 libxfixes3 \
    libxrandr2 libgbm1 libasound2

WORKDIR /app
COPY . .

# تثبيت المكتبات والمتصفحات
RUN pip install -r requirements.txt
RUN playwright install chromium
RUN playwright install-deps

# تشغيل السيرفر
CMD ["python", "main.py"]
