FROM python:3.12

RUN mkdir /app/
WORKDIR /app

COPY src/EConnectionService ./src/EConnectionService
COPY pyproject.toml ./
COPY README.md ./
COPY requirements.txt ./

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
&& apt-get install -y glpk-utils \
&& apt-get clean
RUN pip install -r requirements.txt
RUN pip install ./
ENTRYPOINT ["python3", "src/EConnectionService/EConnection.py"]