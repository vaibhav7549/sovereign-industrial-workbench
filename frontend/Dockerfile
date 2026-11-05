# Build stage
FROM node:20-alpine AS build

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

# Relative API base: the browser calls https://<same host>/api/..., which Nginx proxies to the
# backend. Same origin, so no mixed content and no CORS. Override only for unusual setups.
ARG VITE_API_URL=/api
ENV VITE_API_URL=$VITE_API_URL

RUN npm run build

# Production serve stage
FROM nginx:alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
# Refuse to start without certificates (they are bind-mounted at runtime, never baked in).
COPY 10-check-tls-certs.sh /docker-entrypoint.d/10-check-tls-certs.sh
RUN sed -i 's/\r$//' /docker-entrypoint.d/10-check-tls-certs.sh && \
    chmod 755 /docker-entrypoint.d/10-check-tls-certs.sh && \
    mkdir -p /etc/nginx/certs

EXPOSE 80 443

CMD ["nginx", "-g", "daemon off;"]
