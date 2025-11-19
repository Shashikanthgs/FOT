FROM python:3.12

WORKDIR /flaskapi_app

COPY ./backend/requirements.txt .

RUN pip install --no-cache-dir gunicorn && pip install -r requirements.txt

COPY . .

CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:8000", "backend:create_app()"]