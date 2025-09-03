const express = require('express');
const fs = require('fs').promises;
const path = require('path');
const bcrypt = require('bcrypt');
const cors = require('cors');

const app = express();
const PORT = 3000;
const USERS_FILE = path.join(__dirname, 'users.json');

// Middleware
app.use(cors());
app.use(express.json());

// Initialize users.json if it doesn't exist
async function initializeUsersFile() {
    try {
        await fs.access(USERS_FILE);
    } catch (error) {
        await fs.writeFile(USERS_FILE, JSON.stringify([]));
    }
}

// Signup endpoint
app.post('/signup', async (req, res) => {
    try {
        const { email, phone, dob, state, password } = req.body;

        // Server-side validation
        if (!email || !phone || !dob || !state || !password) {
            return res.status(400).json({ error: 'All fields are required' });
        }
        if (phone.length !== 10 || isNaN(phone)) {
            return res.status(400).json({ error: 'Phone number must be 10 digits' });
        }
        if (password.length < 8) {
            return res.status(400).json({ error: 'Password must be at least 8 characters long' });
        }

        // Read existing users
        const usersData = await fs.readFile(USERS_FILE, 'utf8');
        const users = JSON.parse(usersData);

        // Check for duplicate email or phone
        if (users.some(user => user.email === email)) {
            return res.status(400).json({ error: 'Email already registered' });
        }
        if (users.some(user => user.phone === phone)) {
            return res.status(400).json({ error: 'Phone number already registered' });
        }

        // Hash password
        const saltRounds = 10;
        const hashedPassword = await bcrypt.hash(password, saltRounds);

        // Add new user
        const newUser = {
            email,
            phone,
            dob,
            state,
            password: hashedPassword,
            createdAt: new Date().toISOString()
        };
        users.push(newUser);

        // Save updated users
        await fs.writeFile(USERS_FILE, JSON.stringify(users, null, 2));

        res.status(201).json({ message: 'Signup successful' });
    } catch (error) {
        console.error('Signup error:', error);
        res.status(500).json({ error: 'Server error during signup' });
    }
});

// Start server
app.use(express.static(path.join(__dirname, 'public')));
app.listen(PORT, async () => {
    await initializeUsersFile();
    console.log(`Server running on http://localhost:${PORT}`);
});