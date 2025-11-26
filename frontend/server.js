const express = require('express');
const fs = require('fs').promises;
const path = require('path');
const bcrypt = require('bcrypt');
const cors = require('cors');

const app = express();
const PORT = process.env.PORT || 3000;                    // ← Use env port (required on most prod hosts)
const USERS_FILE = path.join(__dirname, 'users.json');

// Middleware
app.use(cors({
  origin: process.env.CORS_ORIGIN || '*'                  // ← Restrict in prod if needed
}));
app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

// Initialize users.json if missing
async function initializeUsersFile() {
  try {
    await fs.access(USERS_FILE);
  } catch {
    await fs.writeFile(USERS_FILE, JSON.stringify([]));
  }
}

// Start server
app.listen(PORT, async () => {
  await initializeUsersFile();
  console.log(`Server running on port ${PORT}`);
});