FROM python:3.10-slim
WORKDIR /app
COPY ./requirements-plain.txt /app
RUN pip install -r requirements-plain.txt
COPY . .
EXPOSE 8001
CMD ["python", "websockets"]
