FROM python:3.11-alpine

# Bash for convenience :)
RUN apk update && apk add bash gdal-dev alpine-sdk cmake apache-arrow-dev py3-pyarrow
RUN pip install poetry

WORKDIR app

COPY pyproject.toml pyproject.toml
COPY poetry.lock poetry.lock
COPY README.md README.md
RUN poetry install --no-root
COPY fiboa_sda fiboa_sda

ENTRYPOINT ["poetry", "run"]
CMD ["fiboa-sda"]