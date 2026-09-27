FROM python:3.12-slim AS dependencies
WORKDIR /app
ARG REQUIREMENTS_FILE=requirements.txt
COPY ${REQUIREMENTS_FILE} /tmp/requirements.txt
# Keep the existing development manifest; omit pytest tooling from production.
RUN sed '/^[Pp][Yy][Tt][Ee][Ss][Tt]/d' /tmp/requirements.txt > /tmp/runtime-requirements.txt \
    && pip install --no-cache-dir -r /tmp/runtime-requirements.txt

RUN useradd -u 1001 -m appuser && chown appuser:appuser /app

FROM dependencies AS dev
RUN pip install --no-cache-dir -r /tmp/requirements.txt watchfiles==1.3.0
COPY --chown=appuser:appuser services/notification-service/ /app/
COPY --chown=appuser:appuser shared/ /shared/
COPY --chown=appuser:appuser shared/ /app/shared/
USER appuser
EXPOSE 8109
CMD ["sh", "-c", "exec watchfiles --target-type command 'python app.py' /app /shared"]

FROM dependencies AS production
COPY . .
EXPOSE 8109
USER appuser
CMD ["python", "app.py"]
