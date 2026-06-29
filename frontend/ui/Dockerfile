# --- Stage 1: Node Assets Engine ---
FROM node:20-alpine as builder

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# Pass the build argument down from docker-compose config blocks
ARG VITE_API_URL
ENV VITE_API_URL=${VITE_API_URL}

RUN npm run build

# --- Stage 2: Production Nginx Routing Layer ---
FROM nginx:1.27-alpine

# Purge default configuration allocations
RUN rm -rf /usr/share/nginx/html/*

# Direct compiled bundle into Nginx hosting directories
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]