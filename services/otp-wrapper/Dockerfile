FROM python:3.12-slim AS dependencies
WORKDIR /app
COPY requirements.txt /tmp/requirements.txt
# Keep the existing development manifest; omit pytest tooling from production.
RUN sed '/^[Pp][Yy][Tt][Ee][Ss][Tt]/d' /tmp/requirements.txt > /tmp/runtime-requirements.txt \
    && pip install --no-cache-dir -r /tmp/runtime-requirements.txt

RUN useradd -u 1001 -m appuser && chown appuser:appuser /app

FROM dependencies AS dev
RUN pip install --no-cache-dir -r /tmp/requirements.txt watchfiles==1.3.0
USER appuser
EXPOSE 5000
CMD ["sh", "-c", "exec watchfiles --target-type command 'gunicorn --bind 0.0.0.0:5000 app:app' /app /shared"]

FROM dependencies AS production
COPY . .
EXPOSE 5000
USER appuser
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]
