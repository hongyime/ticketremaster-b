FROM python:3.12-slim AS dependencies
WORKDIR /app
COPY orchestrators/transfer-orchestrator/requirements.txt /tmp/requirements.txt
# Keep the existing development manifest; omit pytest tooling from production.
RUN sed '/^[Pp][Yy][Tt][Ee][Ss][Tt]/d' /tmp/requirements.txt > /tmp/runtime-requirements.txt \
    && pip install --no-cache-dir -r /tmp/runtime-requirements.txt

FROM dependencies AS dev
RUN pip install --no-cache-dir -r /tmp/requirements.txt watchfiles==1.3.0
EXPOSE 5000
CMD ["sh", "-c", "exec watchfiles --target-type command 'gunicorn -w 1 -b 0.0.0.0:5000 app:app' /app /shared"]

FROM dependencies AS production
COPY orchestrators/transfer-orchestrator/ .
COPY shared/ ./shared/
EXPOSE 5000
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "app:app"]
