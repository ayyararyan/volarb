FROM node:22-alpine
WORKDIR /app
COPY package.json ./
RUN npm install --omit=dev
COPY src ./src
ENV NODE_ENV=production
ENV MCP_HOST=0.0.0.0
ENV MCP_PORT=3000
EXPOSE 3000
CMD ["npm", "start"]
