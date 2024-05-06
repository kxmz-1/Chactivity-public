FROM python:3.11
WORKDIR /app
COPY pyproject.toml poetry.lock .
RUN pip install poetry && poetry install --no-root --no-directory
COPY . .
RUN poetry install --with=dev
ENTRYPOINT ["poetry", "run" ,"python", "cli.py"]
