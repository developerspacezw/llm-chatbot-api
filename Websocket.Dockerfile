FROM python:3.10-slim
WORKDIR /app
RUN pip install --no-cache-dir \
        confluent-kafka==2.6.0 \
        elastic-apm==6.15.0
        websockets==13.0 \
        python-dotenv==1.0.0 \

COPY . .
EXPOSE 8001
CMD ["python", "websockets"]