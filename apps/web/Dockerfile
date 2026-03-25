FROM node:22-alpine
WORKDIR /app

# Copy root workspace manifests
COPY package.json package-lock.json ./

# Copy all workspace package manifests (needed for npm ci to resolve workspaces)
COPY packages/types/package.json ./packages/types/
COPY packages/api-client/package.json ./packages/api-client/
COPY packages/ui/package.json ./packages/ui/
COPY packages/i18n/package.json ./packages/i18n/
COPY apps/web/package.json ./apps/web/

# Install all workspace dependencies from root
RUN npm ci

# Copy source files
COPY packages/ ./packages/
COPY apps/web/ ./apps/web/

WORKDIR /app/apps/web
CMD ["npm", "run", "dev"]
