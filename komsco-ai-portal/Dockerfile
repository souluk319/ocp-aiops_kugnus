FROM registry.access.redhat.com/ubi9/nodejs-22:latest AS build
USER root
WORKDIR /usr/src/app
ENV VITE_AIOPS_AUTH_MODE=proxy

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM registry.access.redhat.com/ubi9/nginx-120:latest

COPY --from=build /usr/src/app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/nginx.conf

USER 1001

ENTRYPOINT ["nginx", "-e", "/dev/stderr", "-g", "daemon off;"]
