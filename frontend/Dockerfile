FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install

FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# Bake the backend URL into the client bundle (Next inlines NEXT_PUBLIC_* at build).
ARG NEXT_PUBLIC_API_URL=https://ai-workforce-746155486511.europe-west1.run.app
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
# Stamp the deploying commit so the UI can show which build is live (proves a
# merge actually reached the site). Defaults to "dev" for local builds.
ARG NEXT_PUBLIC_BUILD_SHA=dev
ENV NEXT_PUBLIC_BUILD_SHA=$NEXT_PUBLIC_BUILD_SHA
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
EXPOSE 8080
CMD ["node", "server.js"]
