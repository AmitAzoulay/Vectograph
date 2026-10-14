# Frontend image - Node 20 for a modern Vite toolchain.
FROM node:20-alpine

WORKDIR /app

# Install dependencies first so Docker can cache this layer.
# `package*.json` copies the lockfile too when present for reproducible builds.
COPY package*.json ./
RUN npm install

# Copy build config and source.
COPY index.html vite.config.js tailwind.config.js postcss.config.js ./
COPY src ./src

EXPOSE 5173

# `--host` is required for the dev server to be reachable from outside the container.
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]
