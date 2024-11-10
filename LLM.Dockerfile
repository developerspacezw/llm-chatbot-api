FROM python:3.9-slim-buster
WORKDIR /app
COPY ./requirements.txt /app
RUN pip install -r requirements.txt
COPY ./llm_run_server.py .
COPY ./jsonSerializer jsonSerializer
COPY ./schemas schemas
COPY ./preload_llm.py .
RUN python preload_llm.py
CMD ["python", "llm_run_server.py"]