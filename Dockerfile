FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/logs && chmod 777 /app/logs

EXPOSE 5000

CMD ["python", "v2.py"]
