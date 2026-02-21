# PixelForge Frontend — multi-stage build
# Stage 1: Build
FROM node:20-alpine AS build

WORKDIR /app
COPY package.json ./
RUN npm install
COPY . .

# Route API calls through the nginx proxy (/api → backend:8000)
ENV VITE_API_URL=/api

RUN npm run build

# Stage 2: Serve with nginx
FROM nginx:alpine

# Copy custom nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy built assets
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
