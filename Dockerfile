# ========================================
# Build flask image
# ========================================
FROM python:3.12-slim AS builder

WORKDIR /usr/src/app
# set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

COPY requirements.txt ./
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /usr/src/app/wheels -r requirements.txt

#########
# FINAL
#########
# pull official base image
FROM python:3.12-slim
# set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /code

# install dependencies
COPY --from=builder /usr/src/app/wheels /wheels
RUN pip install --no-cache /wheels/*

# Not sure why wheels are not avaialble for this module.
RUN pip install connexion[flask,uvicorn]

# copy project
COPY . ./

RUN chmod u+x start.sh

EXPOSE 5000 9090

CMD ["./start.sh"]
