FROM python:3.13-slim
LABEL org.opencontainers.image.title="CommonGround"
LABEL org.opencontainers.image.authors="Isaac Shiloah Herbert V, ISAAC.INCOGNITO007 <isaac.incognito007@gmail.com>"
WORKDIR /app
RUN groupadd --gid 10001 ground && useradd --uid 10001 --gid ground --no-create-home ground && mkdir /data && chown ground:ground /data
COPY --chown=ground:ground . /app
USER ground
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 CG_DB=/data/commonground.sqlite3 CG_HOST=0.0.0.0 PORT=8000
EXPOSE 8000
VOLUME /data
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health',timeout=3)" || exit 1
CMD ["python", "server.py"]
