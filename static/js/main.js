/*
 * JavaScript functions for the attendance application.
 * Obtains the user's geolocation and submits punch data to the server.
 */

/**
 * Display a message to the user.
 * @param {string} text - The message text.
 * @param {string} type - Bootstrap alert type ('success', 'danger', 'info').
 */
function showMessage(text, type) {
    const messageDiv = document.getElementById('message');
    messageDiv.innerHTML = `<div class="alert alert-${type}" role="alert">${text}</div>`;
}

/**
 * Submit a punch action to the server.
 * @param {string} action - Either 'in' or 'out'.
 */
function submitPunch(action) {
    const employeeId = document.getElementById('employeeId').value.trim();
    if (!employeeId) {
        showMessage('Please enter your employee ID.', 'danger');
        return;
    }

    if (!navigator.geolocation) {
        showMessage('Geolocation is not supported by your browser.', 'danger');
        return;
    }

    // Request current position
    navigator.geolocation.getCurrentPosition(
        (position) => {
            const { latitude, longitude } = position.coords;
            fetch('/punch', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    employee_id: employeeId,
                    action: action,
                    latitude: latitude,
                    longitude: longitude
                })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    showMessage(data.message, 'success');
                } else {
                    showMessage(data.message || 'Failed to record punch.', 'danger');
                }
            })
            .catch(() => {
                showMessage('Error submitting punch. Please try again.', 'danger');
            });
        },
        (error) => {
            let errorMessage = 'Unable to retrieve your location.';
            switch (error.code) {
                case error.PERMISSION_DENIED:
                    errorMessage = 'Please allow location access to record attendance.';
                    break;
                case error.POSITION_UNAVAILABLE:
                    errorMessage = 'Location information is unavailable.';
                    break;
                case error.TIMEOUT:
                    errorMessage = 'The request to get your location timed out.';
                    break;
            }
            showMessage(errorMessage, 'danger');
        }
    );
}