
FROM python:3.6-alpine

LABEL description="Bootstrapper-UI"
LABEL version="2.0"
LABEL maintainer="nembery@paloaltonetworks.com"
ENV CNC_USERNAME=paloalto
ENV CNC_PASSWORD=bootstrapper
WORKDIR /app

COPY src /app/src
COPY cnc /app/cnc

ADD requirements.txt /app/requirements.txt
#ADD cnc/requirements.txt /app/cnc/requirements.txt
RUN apk add --update --no-cache git gcc musl-dev python3-dev libffi-dev openssl-dev \
    && pip install --upgrade pip && pip install --no-cache-dir  -r requirements.txt \
    && apk del --no-cache gcc \
    && if [ -f /app/cnc/db.sqlite3 ]; then rm /app/cnc/db.sqlite3; fi \
    && python /app/cnc/manage.py migrate \
    && python /app/cnc/manage.py shell -c "from django.contrib.auth.models import User; User.objects.create_superuser('${CNC_USERNAME}', 'admin@example.com', '${CNC_PASSWORD}')"

EXPOSE 80
CMD ["python", "/app/cnc/manage.py", "runserver", "0.0.0.0:80"]
