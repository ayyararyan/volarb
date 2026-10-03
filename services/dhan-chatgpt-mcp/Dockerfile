# Build from the repository root so canonical shared contracts retain their paths:
# docker build -f services/dhan-chatgpt-mcp/Dockerfile -t volarb-dhan-mcp .
FROM node:26.5.0-alpine
WORKDIR /app/services/dhan-chatgpt-mcp
COPY --chown=node:node services/dhan-chatgpt-mcp/package.json services/dhan-chatgpt-mcp/package-lock.json ./
RUN npm install --global npm@11.17.0 --ignore-scripts --no-audit --no-fund \
    && npm ci --omit=dev --ignore-scripts --no-audit --no-fund
COPY --chown=node:node services/dhan-chatgpt-mcp/src ./src
COPY --chown=node:node execution-engine /app/execution-engine
RUN mkdir -p /data/dhan && chown -R node:node /data
ENV NODE_ENV=production MCP_HOST=0.0.0.0 MCP_PORT=3000 VOLARB_DATA_DIR=/data
ENV DHAN_PROVIDER_COMMANDS_ENABLED=false DHAN_EXECUTION_ENABLED=false DHAN_BROWSER_RECOVERY_ENABLED=false
USER node
RUN node --input-type=module -e "import('./src/dhan-runtime.mjs')"
EXPOSE 3000
CMD ["npm", "start"]
