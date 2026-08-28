FROM node:20-alpine

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

EXPOSE 3005
CMD ["npm", "run", "start"]
