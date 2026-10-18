FROM node:20.17.0-alpine3.20 AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install --no-audit --no-fund; fi

FROM node:20.17.0-alpine3.20 AS builder
WORKDIR /app
ARG GRAPHGUARD_API_URL=http://localhost:8000
ENV GRAPHGUARD_API_URL=$GRAPHGUARD_API_URL
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:20.17.0-alpine3.20 AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV PORT=3000
RUN addgroup --system --gid 1001 nodejs && adduser --system --uid 1001 nextjs
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
USER nextjs
EXPOSE 3000
CMD ["node", "server.js"]
