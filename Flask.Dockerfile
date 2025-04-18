FROM python:3.9-slim-buster
WORKDIR /app
COPY ./requirements-plain.txt /app
RUN pip install -r requirements-plain.txt
COPY . .
EXPOSE 5000
ENV FLASK_APP=bot.py
CMD ["flask", "run", "--host", "0.0.0.0"]
