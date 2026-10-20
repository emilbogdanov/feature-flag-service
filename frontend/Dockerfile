# The compose stack's proxy: nginx in front of the API instances, also serving the dashboard's
# production build under /dashboard/. Built from the repository root.

FROM node:24-alpine AS build
WORKDIR /frontend
# Dependencies first, so a change to the dashboard alone reuses this layer.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
# Only the bundle: type checking and tests are CI's job, before an image is ever built.
RUN npx vite build

FROM nginx:1.29-alpine
COPY deploy/nginx.conf /etc/nginx/nginx.conf
COPY --from=build /frontend/dist /usr/share/nginx/dashboard
