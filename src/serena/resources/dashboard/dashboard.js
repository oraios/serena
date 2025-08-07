class LogMessage {
    constructor(message, toolNames) {
        message = this.escapeHtml(message);
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

    escapeHtml (convertString) {
        if (typeof convertString !== 'string') return convertString; 

        const patterns = {
            '<'  : '&lt;',
            '>'  : '&gt;',
            '&'  : '&amp;',
            '"'  : '&quot;',
            '\'' : '&#x27;',
            '`'  : '&#x60;'
        };

        return convertString.replace(/[<>&"'`]/g, match => patterns[match]);
  };
}

class Dashboard {
    constructor() {
        let self = this;

        this.toolNames = [];
        this.currentMaxIdx = -1;
        this.pollInterval = null;
        this.failureCount = 0;
        this.$logContainer = $('#log-container');
        this.$errorContainer = $('#error-container');
        this.$loadButton = $('#load-logs');
        this.$shutdownButton = $('#shutdown');
        this.$toggleStats = $('#toggle-stats');
        this.$statsSection = $('#stats-section');
        this.$refreshStats = $('#refresh-stats');
        this.$clearStats = $('#clear-stats');
        this.$themeToggle = $('#theme-toggle');
        this.$themeIcon = $('#theme-icon');
        this.$themeText = $('#theme-text');

        this.countChart = null;
        this.tokensChart = null;
        this.inputChart = null;
        this.outputChart = null;

        // register event handlers
        this.$loadButton.click(this.loadLogs.bind(this));
        this.$shutdownButton.click(this.shutdown.bind(this));
        this.$toggleStats.click(this.toggleStats.bind(this));
        this.$refreshStats.click(this.loadStats.bind(this));
        this.$clearStats.click(this.clearStats.bind(this));
        this.$themeToggle.click(this.toggleTheme.bind(this));

        // initialize theme
        this.initializeTheme();

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
                self.failureCount = 0;
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
                self.failureCount++;
                if (self.failureCount >= 3) {
                    console.log('Server appears to be down, closing tab');
                    window.close();
                }
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
        $.when(
            $.ajax({ url: '/get_tool_stats', type: 'GET' }),
            $.ajax({ url: '/get_token_count_estimator_name', type: 'GET' })
        ).done(function(statsResp, estimatorResp) {
            const stats = statsResp[0].stats;
            const tokenCountEstimatorName = estimatorResp[0].token_count_estimator_name;
            self.displayStats(stats, tokenCountEstimatorName);
        }).fail(function() {
            console.error('Error loading stats or estimator name');
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

    displayStats(stats, tokenCountEstimatorName) {
        const names = Object.keys(stats);
      // If no stats collected
        if (names.length === 0) {
            // hide summary, charts, estimator name
            $('#stats-summary').hide();
            $('#estimator-name').hide();
            $('.charts-container').hide();
            // show no-stats message
            $('#no-stats-message').show();
            return;
        } else {
            // Ensure everything is visible
            $('#estimator-name').show();
            $('#stats-summary').show();
            $('.charts-container').show();
            $('#no-stats-message').hide();
        }

        $('#estimator-name').html(`<strong>Token count estimator:</strong> ${tokenCountEstimatorName}`);

        const counts = names.map(n => stats[n].num_times_called);
        const inputTokens = names.map(n => stats[n].input_tokens);
        const outputTokens = names.map(n => stats[n].output_tokens);
        const totalTokens = names.map(n => stats[n].input_tokens + stats[n].output_tokens);
        
        // Calculate totals for summary table
        const totalCalls = counts.reduce((sum, count) => sum + count, 0);
        const totalInputTokens = inputTokens.reduce((sum, tokens) => sum + tokens, 0);
        const totalOutputTokens = outputTokens.reduce((sum, tokens) => sum + tokens, 0);
        
        // Generate consistent colors for tools
        const colors = this.generateColors(names.length);

        const countCtx = document.getElementById('count-chart');
        const tokensCtx = document.getElementById('tokens-chart');
        const inputCtx = document.getElementById('input-chart');
        const outputCtx = document.getElementById('output-chart');

        if (this.countChart) this.countChart.destroy();
        if (this.tokensChart) this.tokensChart.destroy();
        if (this.inputChart) this.inputChart.destroy();
        if (this.outputChart) this.outputChart.destroy();

        // Update summary table
        this.updateSummaryTable(totalCalls, totalInputTokens, totalOutputTokens);

        // Register datalabels plugin
        Chart.register(ChartDataLabels);

        // Get theme-aware colors
        const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
        const textColor = isDark ? '#ffffff' : '#000000';
        const gridColor = isDark ? '#444' : '#ddd';

        // Tool calls pie chart
        this.countChart = new Chart(countCtx, {
            type: 'pie',
            data: { 
                labels: names, 
                datasets: [{ 
                    data: counts,
                    backgroundColor: colors
                }] 
            },
            options: {
                plugins: {
                    legend: { 
                        display: true,
                        labels: {
                            color: textColor
                        }
                    },
                    datalabels: {
                        display: true,
                        color: 'white',
                        font: { weight: 'bold' },
                        formatter: (value) => value
                    }
                }
            }
        });

        // Input tokens pie chart
        this.inputChart = new Chart(inputCtx, {
            type: 'pie',
            data: { 
                labels: names, 
                datasets: [{ 
                    data: inputTokens,
                    backgroundColor: colors
                }] 
            },
            options: {
                plugins: {
                    legend: { 
                        display: true,
                        labels: {
                            color: textColor
                        }
                    },
                    datalabels: {
                        display: true,
                        color: 'white',
                        font: { weight: 'bold' },
                        formatter: (value) => value
                    }
                }
            }
        });

        // Output tokens pie chart
        this.outputChart = new Chart(outputCtx, {
            type: 'pie',
            data: { 
                labels: names, 
                datasets: [{ 
                    data: outputTokens,
                    backgroundColor: colors
                }] 
            },
            options: {
                plugins: {
                    legend: { 
                        display: true,
                        labels: {
                            color: textColor
                        }
                    },
                    datalabels: {
                        display: true,
                        color: 'white',
                        font: { weight: 'bold' },
                        formatter: (value) => value
                    }
                }
            }
        });

        // Combined input/output tokens bar chart
        this.tokensChart = new Chart(tokensCtx, {
            type: 'bar',
            data: { 
                labels: names, 
                datasets: [
                    { 
                        label: 'Input Tokens', 
                        data: inputTokens,
                        backgroundColor: colors.map(color => color + '80'), // Semi-transparent
                        borderColor: colors,
                        borderWidth: 2,
                        borderSkipped: false,
                        yAxisID: 'y'
                    },
                    { 
                        label: 'Output Tokens', 
                        data: outputTokens,
                        backgroundColor: colors,
                        yAxisID: 'y1'
                    }
                ]
            },
            options: {
                responsive: true,
                plugins: {
                    legend: {
                        labels: {
                            color: textColor
                        }
                    }
                },
                scales: {
                    x: {
                        ticks: {
                            color: textColor
                        },
                        grid: {
                            color: gridColor
                        }
                    },
                    y: {
                        type: 'linear',
                        display: true,
                        position: 'left',
                        beginAtZero: true,
                        title: { 
                            display: true, 
                            text: 'Input Tokens',
                            color: textColor
                        },
                        ticks: {
                            color: textColor
                        },
                        grid: {
                            color: gridColor
                        }
                    },
                    y1: {
                        type: 'linear',
                        display: true,
                        position: 'right',
                        beginAtZero: true,
                        title: { 
                            display: true, 
                            text: 'Output Tokens',
                            color: textColor
                        },
                        ticks: {
                            color: textColor
                        },
                        grid: { 
                            drawOnChartArea: false,
                            color: gridColor
                        }
                    }
                }
            }
        });
    }

    generateColors(count) {
        const colors = [
            '#FF6384', '#36A2EB', '#FFCE56', '#4BC0C0', '#9966FF',
            '#FF9F40', '#FF6384', '#C9CBCF', '#4BC0C0', '#FF6384'
        ];
        return Array.from({length: count}, (_, i) => colors[i % colors.length]);
    }

    updateSummaryTable(totalCalls, totalInputTokens, totalOutputTokens) {
        const tableHtml = `
            <table class="stats-summary">
                <tr><th>Metric</th><th>Total</th></tr>
                <tr><td>Tool Calls</td><td>${totalCalls}</td></tr>
                <tr><td>Input Tokens</td><td>${totalInputTokens}</td></tr>
                <tr><td>Output Tokens</td><td>${totalOutputTokens}</td></tr>
                <tr><td>Total Tokens</td><td>${totalInputTokens + totalOutputTokens}</td></tr>
            </table>
        `;
        $('#stats-summary').html(tableHtml);
    }

    initializeTheme() {
        // Get saved theme from localStorage or default to 'light'
        const savedTheme = localStorage.getItem('serena-theme') || 'light';
        this.setTheme(savedTheme);
    }

    toggleTheme() {
        const currentTheme = document.documentElement.getAttribute('data-theme') || 'light';
        const newTheme = currentTheme === 'light' ? 'dark' : 'light';
        this.setTheme(newTheme);
    }

    setTheme(theme) {
        // Set the theme on the document element
        document.documentElement.setAttribute('data-theme', theme);
        
        // Update the toggle button
        if (theme === 'dark') {
            this.$themeIcon.text('☀️');
            this.$themeText.text('Light');
        } else {
            this.$themeIcon.text('🌙');
            this.$themeText.text('Dark');
        }
        
        // Save to localStorage
        localStorage.setItem('serena-theme', theme);
        
        // Update charts if they exist
        this.updateChartsTheme();
    }

    updateChartsTheme() {
        const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
        const textColor = isDark ? '#ffffff' : '#000000';
        const gridColor = isDark ? '#444' : '#ddd';
        
        // Update existing charts
        if (this.countChart) {
            this.countChart.options.scales.x.ticks.color = textColor;
            this.countChart.options.scales.y.ticks.color = textColor;
            this.countChart.options.scales.x.grid.color = gridColor;
            this.countChart.options.scales.y.grid.color = gridColor;
            this.countChart.update();
        }
        
        if (this.inputChart) {
            this.inputChart.options.scales.x.ticks.color = textColor;
            this.inputChart.options.scales.y.ticks.color = textColor;
            this.inputChart.options.scales.x.grid.color = gridColor;
            this.inputChart.options.scales.y.grid.color = gridColor;
            this.inputChart.update();
        }
        
        if (this.outputChart) {
            this.outputChart.options.scales.x.ticks.color = textColor;
            this.outputChart.options.scales.y.ticks.color = textColor;
            this.outputChart.options.scales.x.grid.color = gridColor;
            this.outputChart.options.scales.y.grid.color = gridColor;
            this.outputChart.update();
        }
        
        if (this.tokensChart) {
            this.tokensChart.options.scales.x.ticks.color = textColor;
            this.tokensChart.options.scales.y.ticks.color = textColor;
            this.tokensChart.options.scales.y1.ticks.color = textColor;
            this.tokensChart.options.scales.x.grid.color = gridColor;
            this.tokensChart.options.scales.y.grid.color = gridColor;
            this.tokensChart.options.scales.y1.grid.color = gridColor;
            this.tokensChart.update();
        }
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
