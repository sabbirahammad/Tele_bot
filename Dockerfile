FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# SQLite ডাটাবেজের জন্য ভলিউম মাউন্ট করার সুবিধা থাকলে ভালো
# অন্যথায় কন্টেইনার রিস্টার্ট হলে ডাটা মুছে যেতে পারে
VOLUME ["/app/database"]

CMD ["python", "main.py"]