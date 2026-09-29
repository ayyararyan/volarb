FROM node:26.5.0-alpine
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm install --global npm@11.17.0 --ignore-scripts --no-audit --no-fund \
    && npm ci --omit=dev --ignore-scripts --no-audit --no-fund
COPY src ./src
RUN mkdir -p /data/dhan && chown -R node:node /data
ENV NODE_ENV=production MCP_HOST=0.0.0.0 MCP_PORT=3000 VOLARB_DATA_DIR=/data
ENV DHAN_EXECUTION_ENABLED=false DHAN_BROWSER_RECOVERY_ENABLED=false
USER node
EXPOSE 3000
CMD ["npm", "start"]
