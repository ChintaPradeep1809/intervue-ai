FROM node:24-alpine AS build
WORKDIR /repo
COPY package.json package-lock.json ./
COPY apps/web/package.json apps/web/
COPY packages/types/package.json packages/types/
COPY packages/config/package.json packages/config/
RUN npm ci
COPY packages ./packages
COPY apps/web ./apps/web
ARG API_INTERNAL_URL=http://api:8100
ENV API_INTERNAL_URL=$API_INTERNAL_URL NEXT_TELEMETRY_DISABLED=1
RUN npm run build -w web

FROM node:24-alpine
WORKDIR /repo
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1
COPY --from=build /repo /repo
USER node
EXPOSE 3000
CMD ["npm", "run", "start", "-w", "web"]
