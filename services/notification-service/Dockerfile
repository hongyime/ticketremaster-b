FROM python:3.12-slim AS dependencies
WORKDIR /app
COPY requirements.txt /tmp/requirements.txt
# Keep the existing development manifest; omit pytest tooling from production.
RUN sed '/^[Pp][Yy][Tt][Ee][Ss][Tt]/d' /tmp/requirements.txt > /tmp/runtime-requirements.txt \
    && pip install --no-cache-dir -r /tmp/runtime-requirements.txt

FROM dependencies AS dev
RUN pip install --no-cache-dir -r /tmp/requirements.txt watchfiles==1.3.0
EXPOSE 8109
CMD ["sh", "-c", "exec watchfiles --target-type command 'python app.py' /app /shared"]

FROM dependencies AS production
COPY . .
EXPOSE 8109
CMD ["python", "app.py"]
