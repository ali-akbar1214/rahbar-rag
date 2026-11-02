# Stage 1: Build & asset preparation
FROM alpine:3.20 AS builder

WORKDIR /src
COPY index.html ./
# Validate static HTML presence
RUN test -f index.html

# Stage 2: Unprivileged Nginx runtime
FROM nginxinc/nginx-unprivileged:1.27-alpine AS runner

USER root
COPY --from=builder /src/index.html /usr/share/nginx/html/index.html
COPY nginx.conf /etc/nginx/nginx.conf

RUN chown -R 101:101 /usr/share/nginx/html && \
    chmod -R 755 /usr/share/nginx/html

USER 101

EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]
