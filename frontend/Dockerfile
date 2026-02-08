FROM node:18-alpine

# Set working directory
WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies (include dev packages required for build)
RUN npm install --legacy-peer-deps

# Copy source code
COPY . .

# Build-time env vars (Vite bakes VITE_* at build time)
ARG VITE_COLLAB_ENABLED=false
ARG VITE_COLLAB_WS=ws://localhost:3001
ENV VITE_COLLAB_ENABLED=$VITE_COLLAB_ENABLED
ENV VITE_COLLAB_WS=$VITE_COLLAB_WS

# Build the application
RUN npm run build

# Remove dev dependencies from node_modules to keep the image lean
RUN npm prune --omit=dev

# Install serve to run the built app
RUN npm install -g serve

# Expose port
EXPOSE 3000

# Start the application
CMD ["serve", "-s", "dist", "-l", "3000"]
