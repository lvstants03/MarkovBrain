FROM python:3.10-slim

WORKDIR /app

# Cai dat dependencies he thong
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements truoc de cache layer Docker
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Copy ma nguon vao container
COPY . .

EXPOSE 8000

# Chay ung dung bang uvicorn
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
