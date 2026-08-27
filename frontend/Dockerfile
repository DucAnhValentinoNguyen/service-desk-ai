FROM node:20-alpine

WORKDIR /app
COPY package.json ./
RUN npm install --no-audit --no-fund
COPY . .

EXPOSE 3005
CMD ["npm", "run", "dev"]
