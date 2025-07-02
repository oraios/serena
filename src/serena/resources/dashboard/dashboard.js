class LogMessage {
    constructor(message, toolNames) {
        const logLevel = this.determineLogLevel(message);
        const highlightedMessage = this.highlightToolNames(message, toolNames);
        this.$elem = $('<div>').addClass('log-' + logLevel).html(highlightedMessage + '\n');
    }

    determineLogLevel(message) {
        if (message.startsWith('DEBUG')) {
            return 'debug';
        } else if (message.startsWith('INFO')) {
            return 'info';
        } else if (message.startsWith('WARNING')) {
            return 'warning';
        } else if (message.startsWith('ERROR')) {
            return 'error';
        } else {
            return 'default';
        }
    }

    highlightToolNames(message, toolNames) {
        let highlightedMessage = message;
        toolNames.forEach(function(toolName) {
            const regex = new RegExp('\\b' + toolName + '\\b', 'gi');
            highlightedMessage = highlightedMessage.replace(regex, '<span class="tool-name">' + toolName + '</span>');
        });
        return highlightedMessage;
    }
}

class Dashboard {
    constructor() {
        let self = this;

        this.toolNames = [];
        this.currentMaxIdx = -1;
        this.pollInterval = null;
        this.$logContainer = $('#log-container');
        this.$errorContainer = $('#error-container');
        this.$loadButton = $('#load-logs');
        this.$shutdownButton = $('#shutdown');
        this.$toggleStats = $('#toggle-stats');
        this.$statsSection = $('#stats-section');
        this.$clearStats = $('#clear-stats');

        this.countChart = null;
        this.inputChart = null;
        this.outputChart = null;

        // register event handlers
        this.$loadButton.click(this.loadLogs.bind(this));
        this.$shutdownButton.click(this.shutdown.bind(this));
        this.$toggleStats.click(this.toggleStats.bind(this));
        this.$clearStats.click(this.clearStats.bind(this));

        // initialize the application
        this.loadToolNames().then(function() {
            // Load logs on page load after tool names are loaded
            self.loadLogs();
        });
    }

    displayLogMessage(message) {
        $('#log-container').append(new LogMessage(message, this.toolNames).$elem);
    }

    loadToolNames() {
        let self = this;
        return $.ajax({
            url: '/get_tool_names',
            type: 'GET',
            success: function(response) {
                self.toolNames = response.tool_names || [];
                console.log('Loaded tool names:', self.toolNames);
            },
            error: function(xhr, status, error) {
                console.error('Error loading tool names:', error);
            }
        });
    }

    loadLogs() {
        console.log("Loading logs");
        let self = this;

        // Disable button and show loading state
        self.$loadButton.prop('disabled', true).text('Loading...');
        self.$errorContainer.empty();

        // Make API call
        $.ajax({
            url: '/get_log_messages',
            type: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({
                start_idx: 0
            }),
            success: function(response) {
                // Clear existing logs
                self.$logContainer.empty();

                // Update max_idx
                self.currentMaxIdx = response.max_idx || -1;

                // Display each log message
                if (response.messages && response.messages.length > 0) {
                    response.messages.forEach(function(message) {
                        self.displayLogMessage(message);
                    });

                    // Auto-scroll to bottom
                    const logContainer = $('#log-container')[0];
                    logContainer.scrollTop = logContainer.scrollHeight;
                } else {
                    $('#log-container').html('<div class="loading">No log messages found.</div>');
                }

                // Start periodic polling for new logs
                self.startPeriodicPolling();
            },
            error: function(xhr, status, error) {
                console.error('Error loading logs:', error);
                self.$errorContainer.html('<div class="error-message">Error loading logs: ' +
                    (xhr.responseJSON ? xhr.responseJSON.detail : error) + '</div>');
            },
            complete: function() {
                // Re-enable button
                self.$loadButton.prop('disabled', false).text('Reload Log');
            }
        });
    }

    pollForNewLogs() {
        let self = this;
        console.log("Polling logs", this.currentMaxIdx);
        $.ajax({
            url: '/get_log_messages',
            type: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({
                start_idx: self.currentMaxIdx + 1
            }),
            success: function(response) {
                // Only append new messages if we have any
                if (response.messages && response.messages.length > 0) {
                    let wasAtBottom = false;
                    const logContainer = $('#log-container')[0];

                    // Check if user was at the bottom before adding new logs
                    if (logContainer.scrollHeight > 0) {
                        wasAtBottom = (logContainer.scrollTop + logContainer.clientHeight) >= (logContainer.scrollHeight - 10);
                    }

                    // Append new messages
                    response.messages.forEach(function(message) {
                        self.displayLogMessage(message);
                    });

                    // Update max_idx
                    self.currentMaxIdx = response.max_idx || self.currentMaxIdx;

                    // Auto-scroll to bottom if user was already at bottom
                    if (wasAtBottom) {
                        logContainer.scrollTop = logContainer.scrollHeight;
                    }
                } else {
                    // Update max_idx even if no new messages
                    self.currentMaxIdx = response.max_idx || self.currentMaxIdx;
                }
            },
            error: function(xhr, status, error) {
                console.error('Error polling for new logs:', error);
            }
        });
    }

    startPeriodicPolling() {
        // Clear any existing interval
        if (this.pollInterval) {
            clearInterval(this.pollInterval);
        }

        // Start polling every second (1000ms)
        this.pollInterval = setInterval(this.pollForNewLogs.bind(this), 1000);
    }

    toggleStats() {
        if (this.$statsSection.is(':visible')) {
            this.$statsSection.hide();
            this.$toggleStats.text('Show Stats');
        } else {
            this.$statsSection.show();
            this.$toggleStats.text('Hide Stats');
            this.loadStats();
        }
    }

    loadStats() {
        let self = this;
        $.ajax({
            url: '/get_tool_stats',
            type: 'GET',
            success: function(response) {
                self.displayStats(response.stats || {});
            },
            error: function(xhr, status, error) {
                console.error('Error loading stats:', error);
            }
        });
    }

    clearStats() {
        let self = this;
        $.ajax({
            url: '/clear_tool_stats',
            type: 'POST',
            success: function() {
                self.loadStats();
            },
            error: function(xhr, status, error) {
                console.error('Error clearing stats:', error);
            }
        });
    }

    displayStats(stats) {
        const names = Object.keys(stats);
        const counts = names.map(n => stats[n].count);
        const inputChars = names.map(n => stats[n].input_chars);
        const outputChars = names.map(n => stats[n].output_chars);

        const countCtx = document.getElementById('count-chart');
        const inputCtx = document.getElementById('input-chart');
        const outputCtx = document.getElementById('output-chart');

        if (this.countChart) this.countChart.destroy();
        if (this.inputChart) this.inputChart.destroy();
        if (this.outputChart) this.outputChart.destroy();

        if (names.length === 0) {
            this.countChart = null;
            this.inputChart = null;
            this.outputChart = null;
            countCtx.getContext('2d').clearRect(0,0,countCtx.width,countCtx.height);
            inputCtx.getContext('2d').clearRect(0,0,inputCtx.width,inputCtx.height);
            outputCtx.getContext('2d').clearRect(0,0,outputCtx.width,outputCtx.height);
            return;
        }

        this.countChart = new Chart(countCtx, {
            type: 'pie',
            data: { labels: names, datasets: [{ data: counts }] },
        });

        this.inputChart = new Chart(inputCtx, {
            type: 'bar',
            data: { labels: names, datasets: [{ label: 'Input Chars', data: inputChars }] },
            options: { scales: { y: { beginAtZero: true } } }
        });

        this.outputChart = new Chart(outputCtx, {
            type: 'bar',
            data: { labels: names, datasets: [{ label: 'Output Chars', data: outputChars }] },
            options: { scales: { y: { beginAtZero: true } } }
        });
    }

    shutdown() {
        const self = this;
        const _shutdown = function () {
            console.log("Triggering shutdown");
            $.ajax({
                url: '/shutdown',
                type: "PUT",
                contentType: 'application/json',
            });
            self.$errorContainer.html('<div class="error-message">Shutting down ...</div>')
            setTimeout(function() {
                window.close();
            }, 2000);
        }

        // ask for confirmation using a dialog
        if (confirm("This will fully terminate the Serena server.")) {
            _shutdown();
        } else {
            console.log("Shutdown cancelled");
        }
    }
}
