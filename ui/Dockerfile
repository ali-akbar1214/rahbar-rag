# Stage 1: Build & asset preparation
FROM alpine:3.24 AS builder

WORKDIR /src
COPY index.html ./
# Validate static HTML presence
RUN test -f index.html

# Stage 2: Unprivileged Nginx runtime
FROM nginxinc/nginx-unprivileged:1.31.7-alpine AS runner

USER root
RUN apk upgrade --no-cache
COPY --from=builder /src/index.html /usr/share/nginx/html/index.html
COPY nginx.conf /etc/nginx/nginx.conf

RUN chown -R 101:101 /usr/share/nginx/html && \
    chmod -R 755 /usr/share/nginx/html

USER 101

EXPOSE 8080

ENTRYPOINT ["nginx", "-g", "daemon off;"]
