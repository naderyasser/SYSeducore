/**
 * API Utility for making HTTP requests to Django backend.
 */
const API = {
    
    /**
     * Get CSRF token from cookie
     */
    getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === name + '=') {
                    cookieValue = cookie.substring(name.length + 1);
                    break;
                }
            }
        }
        return cookieValue;
    },
    
    /**
     * Make an API request
     */
    async request(url, options = {}) {
        const csrftoken = this.getCookie('csrftoken');
        
        const defaultOptions = {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrftoken
            },
            credentials: 'same-origin',
        };
        
        const requestOptions = {
            ...defaultOptions,
            ...options
        };
        
        try {
            const response = await fetch(url, requestOptions);
            
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.message || 'Request failed');
            }
            
            return await response.json();
        } catch (error) {
            console.error('API Error:', error);
            throw error;
        }
    },
    
    /**
     * HTTP methods
     */
    get(url, options = {}) {
        return this.request(url, { ...defaultOptions, method: 'GET', ...options });
    },
    
    post(url, data) {
        return this.request(url, { 
            ...defaultOptions, 
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.getCookie('csrftoken'),
            },
            credentials: 'same-origin',
            body: JSON.stringify(data)
        });
    },
    
    put(url, data) {
        return this.request(url, { 
            ...defaultOptions, 
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.getCookie('csrftoken'),
            },
            credentials: 'same-origin',
            body: JSON.stringify(data)
        });
    },
    
    delete(url) {
        return this.request(url, { 
            ...defaultOptions, 
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.getCookie('csrftoken'),
            },
            credentials: 'same-origin',
        });
    },
};
