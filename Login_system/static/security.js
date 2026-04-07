/**
 * OWASP Security Module
 * Implements OWASP Top 10 protections for client-side code
 * 
 * Features:
 * - XSS Prevention (A03:2021 - Injection)
 * - CSRF Protection (A01:2021 - Broken Access Control)
 * - Input Sanitization
 * - Secure DOM manipulation
 */

// ============================================================
// XSS PROTECTION - Use instead of innerHTML
// ============================================================

/**
 * Safely set HTML content with sanitization
 * OWASP A03:2021 - Injection Prevention
 */
function safeSetHTML(element, htmlString) {
    if (typeof element === 'string') {
        element = document.getElementById(element) || document.querySelector(element);
    }
    
    if (!element) {
        console.error('Element not found for safeSetHTML');
        return;
    }
    
    // Create temporary div for parsing
    const temp = document.createElement('div');
    temp.innerHTML = htmlString;
    
    // Remove dangerous attributes
    const dangerous = temp.querySelectorAll('[onclick],[onload],[onerror],[onmouseover]');
    dangerous.forEach(el => {
        el.removeAttribute('onclick');
        el.removeAttribute('onload');
        el.removeAttribute('onerror');
        el.removeAttribute('onmouseover');
    });
    
    // Remove script tags
    const scripts = temp.querySelectorAll('script');
    scripts.forEach(script => script.remove());
    
    // Set sanitized content
    element.innerHTML = temp.innerHTML;
}

/**
 * Safely set text content (no HTML parsing)
 * Use this when you only need text, not HTML
 */
function safeSetText(element, text) {
    if (typeof element === 'string') {
        element = document.getElementById(element) || document.querySelector(element);
    }
    
    if (!element) {
        console.error('Element not found for safeSetText');
        return;
    }
    
    element.textContent = text; // textContent is XSS-safe
}

/**
 * Escape HTML to prevent XSS
 */
function escapeHTML(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

/**
 * Sanitize user input before display
 */
function sanitizeInput(input) {
    if (!input) return '';
    
    return String(input)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#x27;')
        .replace(/\//g, '&#x2F;');
}

// ============================================================
// CSRF PROTECTION
// ============================================================

/**
 * Get CSRF token from cookie
 * OWASP A01:2021 - Broken Access Control Prevention
 */
function getCSRFToken() {
    const name = 'csrf_token=';
    const decodedCookie = decodeURIComponent(document.cookie);
    const cookies = decodedCookie.split(';');
    
    for (let cookie of cookies) {
        cookie = cookie.trim();
        if (cookie.indexOf(name) === 0) {
            return cookie.substring(name.length);
        }
    }
    
    // Fallback: check meta tag
    const metaTag = document.querySelector('meta[name="csrf-token"]');
    if (metaTag) {
        return metaTag.getAttribute('content');
    }
    
    console.warn('CSRF token not found!');
    return null;
}

/**
 * Secure fetch wrapper with CSRF protection
 */
async function secureFetch(url, options = {}) {
    // Add CSRF token to headers
    const csrfToken = getCSRFToken();
    
    options.headers = options.headers || {};
    if (csrfToken) {
        options.headers['X-CSRF-Token'] = csrfToken;
    }
    
    // Add credentials
    options.credentials = options.credentials || 'same-origin';
    
    // Validate URL (prevent SSRF)
    if (!url.startsWith('/') && !url.startsWith(window.location.origin)) {
        console.error('Invalid URL - potential SSRF attack');
        throw new Error('Invalid URL');
    }
    
    try {
        const response = await fetch(url, options);
        
        // Check for authentication errors
        if (response.status === 401 || response.status === 403) {
            console.error('Authentication error');
            window.location.href = '/login';
            return null;
        }
        
        return response;
    } catch (error) {
        console.error('Fetch error:', error.message);
        throw error;
    }
}

/**
 * Secure form submission with CSRF
 */
function secureFormSubmit(formElement, callback) {
    if (typeof formElement === 'string') {
        formElement = document.getElementById(formElement) || document.querySelector(formElement);
    }
    
    if (!formElement) {
        console.error('Form not found');
        return;
    }
    
    formElement.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const formData = new FormData(formElement);
        const csrfToken = getCSRFToken();
        
        // Add CSRF token
        if (csrfToken) {
            formData.append('csrf_token', csrfToken);
        }
        
        if (callback) {
            callback(formData);
        }
    });
}

// ============================================================
// INPUT VALIDATION
// ============================================================

/**
 * Validate email format
 * OWASP A03:2021 - Injection Prevention
 */
function isValidEmail(email) {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email);
}

/**
 * Validate username (alphanumeric, underscore, hyphen)
 */
function isValidUsername(username) {
    const usernameRegex = /^[a-zA-Z0-9_-]{3,20}$/;
    return usernameRegex.test(username);
}

/**
 * Validate password strength
 */
function isStrongPassword(password) {
    // At least 8 chars, 1 uppercase, 1 lowercase, 1 number
    return password.length >= 8 &&
           /[A-Z]/.test(password) &&
           /[a-z]/.test(password) &&
           /[0-9]/.test(password);
}

/**
 * Sanitize filename (prevent directory traversal)
 */
function sanitizeFilename(filename) {
    return filename.replace(/[^a-zA-Z0-9._-]/g, '_');
}

// ============================================================
// SECURITY MONITORING
// ============================================================

/**
 * Log security events (client-side)
 * OWASP A09:2021 - Security Logging
 */
function logSecurityEvent(eventType, details) {
    const event = {
        timestamp: new Date().toISOString(),
        type: eventType,
        details: details,
        userAgent: navigator.userAgent,
        url: window.location.href
    };
    
    // In production, send to server
    console.log('[SECURITY]', event);
    
    // Optionally send to server
    if (window.location.hostname !== 'localhost') {
        secureFetch('/api/security-log', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(event)
        }).catch(err => console.error('Failed to log security event:', err));
    }
}

// ============================================================
// CLICKJACKING PROTECTION
// ============================================================

/**
 * Prevent clickjacking by checking if in iframe
 * OWASP A05:2021 - Security Misconfiguration
 */
function preventClickjacking() {
    if (window.top !== window.self) {
        // Page is in an iframe
        console.warn('Page loaded in iframe - potential clickjacking');
        logSecurityEvent('clickjacking_attempt', {
            referrer: document.referrer,
            parentOrigin: window.location.ancestorOrigins ? window.location.ancestorOrigins[0] : 'unknown'
        });
        
        // Break out of iframe
        window.top.location = window.self.location;
    }
}

// ============================================================
// AUTO-LOGOUT ON INACTIVITY
// ============================================================

let inactivityTimer;
const INACTIVITY_TIMEOUT = 30 * 60 * 1000; // 30 minutes

function resetInactivityTimer() {
    clearTimeout(inactivityTimer);
    inactivityTimer = setTimeout(() => {
        logSecurityEvent('auto_logout', { reason: 'inactivity' });
        alert('You have been logged out due to inactivity.');
        window.location.href = '/logout';
    }, INACTIVITY_TIMEOUT);
}

function initInactivityMonitor() {
    // Reset timer on user activity
    ['mousedown', 'mousemove', 'keypress', 'scroll', 'touchstart', 'click'].forEach(event => {
        document.addEventListener(event, resetInactivityTimer, true);
    });
    
    resetInactivityTimer();
}

// ============================================================
// SECURE LOCAL STORAGE
// ============================================================

/**
 * Securely store data (don't store sensitive data!)
 * OWASP A02:2021 - Cryptographic Failures
 */
const secureStorage = {
    set: function(key, value) {
        if (typeof value === 'object') {
            value = JSON.stringify(value);
        }
        
        // Warn if storing sensitive-looking data
        const sensitiveKeywords = ['password', 'token', 'secret', 'key', 'ssn'];
        if (sensitiveKeywords.some(k => key.toLowerCase().includes(k))) {
            console.warn(`WARNING: Storing potentially sensitive data in localStorage: ${key}`);
            logSecurityEvent('sensitive_storage_warning', { key });
        }
        
        try {
            localStorage.setItem(key, value);
        } catch (e) {
            console.error('Storage error:', e);
        }
    },
    
    get: function(key) {
        try {
            const value = localStorage.getItem(key);
            try {
                return JSON.parse(value);
            } catch {
                return value;
            }
        } catch (e) {
            console.error('Storage retrieval error:', e);
            return null;
        }
    },
    
    remove: function(key) {
        try {
            localStorage.removeItem(key);
        } catch (e) {
            console.error('Storage removal error:', e);
        }
    },
    
    clear: function() {
        try {
            localStorage.clear();
        } catch (e) {
            console.error('Storage clear error:', e);
        }
    }
};

// ============================================================
// INITIALIZATION
// ============================================================

// Auto-initialize security features on page load
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function() {
        preventClickjacking();
        initInactivityMonitor();
        console.log('✅ OWASP Security Module initialized');
    });
} else {
    preventClickjacking();
    initInactivityMonitor();
    console.log('✅ OWASP Security Module initialized');
}

// Expose global API
window.Security = {
    safeSetHTML,
    safeSetText,
    escapeHTML,
    sanitizeInput,
    getCSRFToken,
    secureFetch,
    secureFormSubmit,
    isValidEmail,
    isValidUsername,
    isStrongPassword,
    sanitizeFilename,
    logSecurityEvent,
    secureStorage
};

console.log('🔒 OWASP Security Module loaded');
