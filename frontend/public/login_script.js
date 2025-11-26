// login_script.js
const navbarMenu = document.querySelector(".navbar .links");
const menuBtn = document.querySelector(".menu-btn");
const hideMenuBtn = navbarMenu ? navbarMenu.querySelector(".close-btn") : null;
const showPopupBtn = document.querySelector(".login-btn");
const formPopup = document.querySelector(".form-popup");
const hidePopupBtn = document.querySelector(".form-popup .close-btn");
const loginSignupLink = document.querySelectorAll(".form-box .bottom-link a");
const signupForm = document.querySelector("#signup-form");
const loginForm = document.querySelector("#login-form");

// Simple hash function for demo (not secure for production)
function simpleHash(str) {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
        hash = ((hash << 5) - hash) + str.charCodeAt(i);
        hash |= 0;
    }
    return hash;
}

// Show mobile menu
if (menuBtn) {
    menuBtn.addEventListener("click", () => {
        if (navbarMenu) navbarMenu.classList.toggle("show-menu");
    });
}

// Hide mobile menu
if (hideMenuBtn && menuBtn) {
    hideMenuBtn.addEventListener("click", () => menuBtn.click());
}

// Show form popup
if (showPopupBtn) {
    showPopupBtn.addEventListener("click", () => {
        document.body.classList.toggle("show-popup");
    });
}

// Hide form popup
if (hidePopupBtn) {
    hidePopupBtn.addEventListener("click", () => {
        document.body.classList.remove("show-popup");
        // ensure popup UI state is reset
        if (formPopup) formPopup.classList.remove("show-signup");
    });
}

// Toggle between login and signup forms
if (loginSignupLink && loginSignupLink.length) {
    loginSignupLink.forEach(link => {
        link.addEventListener("click", (e) => {
            e.preventDefault();
            if (!formPopup) return;
            formPopup.classList[link.id === "signup-link" ? 'add' : 'remove']("show-signup");
        });
    });
}

// Determine backend base URL (adjust if you use nginx)
const BASE_URL = (function(){
    // If frontend served at localhost:3000 (nginx), backend is at localhost:8000
    if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
        return `${window.location.protocol}//127.0.0.1:8000`;
    }
    return window.location.origin;
})();


// Handle sign-up form submission
if (signupForm) {
    // Replace signup handler to POST to backend instead of localStorage
    signupForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const formData = new FormData(signupForm);
        const email = formData.get("email");
        const password = simpleHash(formData.get("password")).toString();
        const policy = formData.get("policy") ? true : false;

        if (!email || !password || !policy) {
            alert("Error: All fields are required!");
            return;
        }

        try {
            const resp = await fetch(`${BASE_URL}/api/signup`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    email: email,
                    password: password
                }),
            });
            const data = await resp.json();
            if (!resp.ok) {
                alert('Signup failed: ' + (data.error || resp.statusText));
                return;
            }
            alert(data.message || 'Signup submitted. Admin will review and approve.');
            signupForm.reset();
            formPopup.classList.remove("show-signup");
        } catch (err) {
            console.error('Signup network error:', err);
            alert('Network error while submitting signup. Please try again later.');
        }
    });
}

// Handle login form submission
if (loginForm) {
    loginForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const formData = new FormData(loginForm);
        const email = formData.get("email");
        const password = simpleHash(formData.get("password")).toString();

        try {
            const resp = await fetch(`${BASE_URL}/api/signin`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    email: email,
                    password: password
                }),
            });

            const data = await resp.json();
            if (!resp.ok) {
                alert('Login failed: ' + (data.error || resp.statusText));
                return;
            }
            const user = data.user;
            // Check user status
            if (user.status === "pending") {
                alert("Error: Your account is pending approval. Please wait for admin approval.");
                return;
            }

            if (user.status === "rejected") {
                alert("Error: Your account has been rejected. Contact the admin for assistance.");
                return;
            }

            // Check if account has expired
            if (user.expiryDate) {
                const expiry = new Date(user.expiryDate);
                const now = new Date();
                if (now > expiry) {
                    alert("Error: Your account has expired. Contact the admin to renew.");
                    return;
                }
            }


            alert(data.message || 'Login successful.');
            loginForm.reset();
            document.body.classList.remove("show-popup");
            // With this (use the full user object from backend):
            localStorage.setItem("currentUser", JSON.stringify(data.user));
            document.body.classList.remove("show-popup");
            window.location.href = "main.html";
        } catch (err) {
            console.error('Login network error:', err);
            alert('Network error while logging in. Please try again later.');
        }
    });
}

// Show login form on page load and prevent auto-login
document.addEventListener("DOMContentLoaded", () => {
    localStorage.removeItem("currentUser"); // Clear session
    document.body.classList.add("show-popup");
    if (formPopup) formPopup.classList.remove("show-signup");
});