FROM python:3-alpine
MAINTAINER Egemen Yavuz "melih.egemen.yavuz@sysco.no"
COPY ./service/freshdesk-rest.py /service/freshdesk-rest.py
COPY ./service/requirements.txt /service/requirements.txt

RUN pip install --upgrade pip

RUN pip install -r /service/requirements.txt

EXPOSE 5000/tcp

CMD ["python3", "-u", "./service/freshdesk-rest.py"]
