FROM python:3.12

RUN mkdir /app/
WORKDIR /app

COPY src/EConnectionService ./src/EConnectionService
COPY pyproject.toml ./
COPY README.md ./
COPY requirements.txt ./

RUN pip install -r requirements.txt && \
    pip install ./
ENTRYPOINT ["python3", "src/EConnectionService/EConnection.py"]