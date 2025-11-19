FROM node:20-alpine

WORKDIR /frontend_app

# copy package files first to leverage Docker cache for npm install
COPY ./package.json ./package-lock.json ./users.json ./server.js ./

RUN npm ci --only=production || npm install --only=production

# copy rest of frontend files
COPY ./public ./public

ENV PORT=3000
EXPOSE 3000

# server.js uses PORT env and serves files from ./public
CMD ["npm", "start"]
