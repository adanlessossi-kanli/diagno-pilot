# Stage 1: Install dependencies
FROM node:22-alpine AS deps
WORKDIR /app

# Copy root workspace manifests
COPY package.json package-lock.json ./

# Copy all workspace package manifests (needed for npm ci to resolve workspaces)
COPY packages/types/package.json ./packages/types/
COPY packages/api-client/package.json ./packages/api-client/
COPY packages/ui/package.json ./packages/ui/
COPY packages/i18n/package.json ./packages/i18n/
COPY apps/web/package.json ./apps/web/

RUN npm ci

# Stage 2: Development (used by docker-compose with `npm run dev`)
FROM node:22-alpine AS dev
WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY package.json package-lock.json ./
COPY packages/ ./packages/
COPY apps/web/ ./apps/web/

WORKDIR /app/apps/web
EXPOSE 3000
CMD ["npm", "run", "dev"]

# Stage 3: Build the application
FROM node:22-alpine AS builder
WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY package.json package-lock.json ./
COPY packages/ ./packages/
COPY apps/web/ ./apps/web/

WORKDIR /app/apps/web
RUN npm run build

# Stage 4: Production runner
FROM node:22-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production

# Create non-root user (UID 1001)
RUN adduser --system --uid 1001 nextuser

# Copy standalone build output
COPY --from=builder /app/apps/web/.next/standalone ./
COPY --from=builder /app/apps/web/.next/static ./apps/web/.next/static
COPY --from=builder /app/apps/web/public ./apps/web/public

USER nextuser

EXPOSE 3000
CMD ["node", "apps/web/server.js"]
