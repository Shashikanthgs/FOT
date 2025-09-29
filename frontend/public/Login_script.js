// login_script.js
const navbarMenu = document.querySelector(".navbar .links");
const menuBtn = document.querySelector(".menu-btn");
const hideMenuBtn = navbarMenu.querySelector(".close-btn");
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
menuBtn.addEventListener("click", () => {
    navbarMenu.classList.toggle("show-menu");
});

// Hide mobile menu
hideMenuBtn.addEventListener("click", () => menuBtn.click());

// Show form popup
showPopupBtn.addEventListener("click", () => {
    document.body.classList.toggle("show-popup");
});

// Hide form popup
hidePopupBtn.addEventListener("click", () => showPopupBtn.click());

// Toggle between login and signup forms
loginSignupLink.forEach(link => {
    link.addEventListener("click", (e) => {
        e.preventDefault();
        formPopup.classList[link.id === "signup-link" ? 'add' : 'remove']("show-signup");
    });
});

// Handle sign-up form submission
signupForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const formData = new FormData(signupForm);
    const email = formData.get("email");
    const password = formData.get("password");
    const policy = formData.get("policy") ? true : false;

    if (!email || !password || !policy) {
        alert("Error: All fields are required!");
        return;
    }

    const data = {
        email,
        password: simpleHash(password),
        policy,
        status: "pending",
        id: Date.now().toString() // Unique ID
    };

    let users = JSON.parse(localStorage.getItem("users") || "[]");
    if (users.find(user => user.email === email)) {
        alert("Error: Email already exists!");
        return;
    }

    users.push(data);
    localStorage.setItem("users", JSON.stringify(users));

    // Store pending user
    let pendingUsers = JSON.parse(localStorage.getItem("pendingUsers") || "[]");
    pendingUsers.push({ email, id: data.id });
    localStorage.setItem("pendingUsers", JSON.stringify(pendingUsers));

    alert("Sign-up successful! Awaiting admin approval. Admin can approve/reject at admin.html.");
    signupForm.reset();
    formPopup.classList.remove("show-signup");
    document.body.classList.add("show-popup");
});

// Handle login form submission
loginForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const formData = new FormData(loginForm);
    const email = formData.get("email");
    const password = simpleHash(formData.get("password"));

    const users = JSON.parse(localStorage.getItem("users") || "[]");
    const user = users.find(user => user.email === email && user.password === password);

    if (!user) {
        alert("Error: Invalid email or password!");
        return;
    }

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

    // Successful login
    localStorage.setItem("currentUser", JSON.stringify({ email }));
    alert("Welcome to SOC!");
    document.body.classList.remove("show-popup");
    window.location.href = "main_index.html";
});

// Show login form on page load and prevent auto-login
document.addEventListener("DOMContentLoaded", () => {
    localStorage.removeItem("currentUser"); // Clear session
    document.body.classList.add("show-popup");
    formPopup.classList.remove("show-signup");
});