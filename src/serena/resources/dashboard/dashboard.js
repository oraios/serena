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

        // Page state
        this.currentPage = 'overview';
        this.configData = null;
        this.jetbrainsMode = false;
        this.activeProjectName = null;
        this.languageToRemove = null;
        this.currentMemoryName = null;
        this.originalMemoryContent = null;
        this.memoryContentDirty = false;
        this.memoryToDelete = null;
        this.isAddingLanguage = false;

        // Tool names and stats
        this.toolNames = [];
        this.currentMaxIdx = -1;
        this.pollInterval = null;
        this.configPollInterval = null;
        this.failureCount = 0;

        // jQuery elements
        this.$logContainer = $('#log-container');
        this.$errorContainer = $('#error-container');
        this.$loadButton = $('#load-logs');
        this.$menuToggle = $('#menu-toggle');
        this.$menuDropdown = $('#menu-dropdown');
        this.$menuShutdown = $('#menu-shutdown');
        this.$themeToggle = $('#theme-toggle');
        this.$themeIcon = $('#theme-icon');
        this.$themeText = $('#theme-text');
        this.$configDisplay = $('#config-display');
        this.$basicStatsDisplay = $('#basic-stats-display');
        this.$statsSection = $('#stats-section');
        this.$refreshStats = $('#refresh-stats');
        this.$clearStats = $('#clear-stats');
        this.$projectsDisplay = $('#projects-display');
        this.$projectsHeader = $('#projects-header');
        this.$availableToolsDisplay = $('#available-tools-display');
        this.$availableModesDisplay = $('#available-modes-display');
        this.$availableContextsDisplay = $('#available-contexts-display');
        this.$addLanguageModal = $('#add-language-modal');
        this.$modalLanguageSelect = $('#modal-language-select');
        this.$modalProjectName = $('#modal-project-name');
        this.$modalAddBtn = $('#modal-add-btn');
        this.$modalCancelBtn = $('#modal-cancel-btn');
        this.$modalClose = $('.modal-close');
        this.$removeLanguageModal = $('#remove-language-modal');
        this.$removeLanguageName = $('#remove-language-name');
        this.$removeModalOkBtn = $('#remove-modal-ok-btn');
        this.$removeModalCancelBtn = $('#remove-modal-cancel-btn');
        this.$modalCloseRemove = $('.modal-close-remove');
        this.$editMemoryModal = $('#edit-memory-modal');
        this.$editMemoryName = $('#edit-memory-name');
        this.$editMemoryContent = $('#edit-memory-content');
        this.$editMemorySaveBtn = $('#edit-memory-save-btn');
        this.$editMemoryCancelBtn = $('#edit-memory-cancel-btn');
        this.$modalCloseEditMemory = $('.modal-close-edit-memory');
        this.$deleteMemoryModal = $('#delete-memory-modal');
        this.$deleteMemoryName = $('#delete-memory-name');
        this.$deleteMemoryOkBtn = $('#delete-memory-ok-btn');
        this.$deleteMemoryCancelBtn = $('#delete-memory-cancel-btn');
        this.$modalCloseDeleteMemory = $('.modal-close-delete-memory');

        // Chart references
        this.countChart = null;
        this.tokensChart = null;
        this.inputChart = null;
        this.outputChart = null;

        // Register event handlers
        this.$loadButton.click(this.loadLogs.bind(this));
        this.$menuShutdown.click(function(e) {
            e.preventDefault();
            self.shutdown();
        });
        this.$menuToggle.click(this.toggleMenu.bind(this));
        this.$themeToggle.click(this.toggleTheme.bind(this));
        this.$refreshStats.click(this.loadStats.bind(this));
        this.$clearStats.click(this.clearStats.bind(this));
        this.$modalAddBtn.click(this.addLanguageFromModal.bind(this));
        this.$modalCancelBtn.click(this.closeLanguageModal.bind(this));
        this.$modalClose.click(this.closeLanguageModal.bind(this));
        this.$removeModalOkBtn.click(this.confirmRemoveLanguageOk.bind(this));
        this.$removeModalCancelBtn.click(this.closeRemoveLanguageModal.bind(this));
        this.$modalCloseRemove.click(this.closeRemoveLanguageModal.bind(this));
        this.$editMemorySaveBtn.click(this.saveMemoryFromModal.bind(this));
        this.$editMemoryCancelBtn.click(this.closeEditMemoryModal.bind(this));
        this.$modalCloseEditMemory.click(this.closeEditMemoryModal.bind(this));
        this.$editMemoryContent.on('input', this.trackMemoryChanges.bind(this));
        this.$deleteMemoryOkBtn.click(this.confirmDeleteMemoryOk.bind(this));
        this.$deleteMemoryCancelBtn.click(this.closeDeleteMemoryModal.bind(this));
        this.$modalCloseDeleteMemory.click(this.closeDeleteMemoryModal.bind(this));

        // Page navigation
        $('[data-page]').click(function(e) {
            e.preventDefault();
            const page = $(this).data('page');
            self.navigateToPage(page);
        });

        // Close menu when clicking outside
        $(document).click(function(e) {
            if (!$(e.target).closest('.header-nav').length) {
                self.$menuDropdown.hide();
            }
        });

        // Close modals when clicking outside
        this.$addLanguageModal.click(function(e) {
            if ($(e.target).hasClass('modal')) {
                self.closeLanguageModal();
            }
        });

        this.$removeLanguageModal.click(function(e) {
            if ($(e.target).hasClass('modal')) {
                self.closeRemoveLanguageModal();
            }
        });

        this.$editMemoryModal.click(function(e) {
            if ($(e.target).hasClass('modal')) {
                self.closeEditMemoryModal();
            }
        });

        this.$deleteMemoryModal.click(function(e) {
            if ($(e.target).hasClass('modal')) {
                self.closeDeleteMemoryModal();
            }
        });

        // Collapsible sections
        $('.collapsible-header').click(function() {
            const $header = $(this);
            const $content = $header.next('.collapsible-content');
            const $icon = $header.find('.toggle-icon');

            $content.slideToggle(300);
            $icon.toggleClass('expanded');
        });

        // Initialize theme
        this.initializeTheme();

        // Add ESC key handler for closing modals
        $(document).keydown(function(e) {
            if (e.key === 'Escape' || e.keyCode === 27) {
                if (self.$addLanguageModal.is(':visible')) {
                    self.closeLanguageModal();
                } else if (self.$removeLanguageModal.is(':visible')) {
                    self.closeRemoveLanguageModal();
                } else if (self.$editMemoryModal.is(':visible')) {
                    self.closeEditMemoryModal();
                } else if (self.$deleteMemoryModal.is(':visible')) {
                    self.closeDeleteMemoryModal();
                }
            }
        });

        // Initialize the application
        this.loadToolNames().then(function() {
            // Start on overview page
            self.loadConfigOverview();
            self.startConfigPolling();
        });
    }

    toggleMenu() {
        this.$menuDropdown.toggle();
    }

    navigateToPage(page) {
        // Hide menu
        this.$menuDropdown.hide();

        // Hide all pages
        $('.page-view').hide();

        // Show selected page
        $('#page-' + page).show();

        // Update menu active state
        $('[data-page]').removeClass('active');
        $('[data-page="' + page + '"]').addClass('active');

        // Update current page
        this.currentPage = page;

        // Stop all polling
        this.stopPolling();

        // Start appropriate polling for the page
        if (page === 'overview') {
            this.loadConfigOverview();
            this.startConfigPolling();
        } else if (page === 'logs') {
            this.loadLogs();
        } else if (page === 'stats') {
            this.loadStats();
        }
    }

    stopPolling() {
        if (this.pollInterval) {
            clearInterval(this.pollInterval);
            this.pollInterval = null;
        }
        if (this.configPollInterval) {
            clearInterval(this.configPollInterval);
            this.configPollInterval = null;
        }
    }

    // ===== Config Overview Methods =====

    loadConfigOverview() {
        let self = this;
        $.ajax({
            url: '/get_config_overview',
            type: 'GET',
            success: function(response) {
                console.log('Config overview response:', response);
                self.failureCount = 0;
                self.configData = response;
                self.jetbrainsMode = response.jetbrains_mode;
                self.activeProjectName = response.active_project.name;
                self.displayConfig(response);
                self.displayBasicStats(response.tool_stats_summary);
                self.displayProjects(response.registered_projects);
                self.displayAvailableTools(response.available_tools);
                self.displayAvailableModes(response.available_modes);
                self.displayAvailableContexts(response.available_contexts);
            },
            error: function(xhr, status, error) {
                console.error('Error loading config overview:', error);
                self.failureCount++;
                if (self.failureCount >= 3) {
                    console.log('Server appears to be down, closing tab');
                    window.close();
                }
                self.$configDisplay.html('<div class="error-message">Error loading configuration</div>');
                self.$basicStatsDisplay.html('<div class="error-message">Error loading stats</div>');
                self.$projectsDisplay.html('<div class="error-message">Error loading projects</div>');
                self.$availableToolsDisplay.html('<div class="error-message">Error loading tools</div>');
                self.$availableModesDisplay.html('<div class="error-message">Error loading modes</div>');
                self.$availableContextsDisplay.html('<div class="error-message">Error loading contexts</div>');
            }
        });
    }

    startConfigPolling() {
        // Poll every 2 seconds for config updates
        this.configPollInterval = setInterval(this.loadConfigOverview.bind(this), 2000);
    }

    displayConfig(config) {
        try {
            // Check if tools and memories sections are currently expanded
            const $existingToolsContent = $('#tools-content');
            const $existingMemoriesContent = $('#memories-content');
            const wasToolsExpanded = $existingToolsContent.is(':visible');
            const wasMemoriesExpanded = $existingMemoriesContent.is(':visible');

            let html = '<div class="config-grid">';

        // Project info
        html += '<div class="config-label">Active Project:</div>';
        if (config.active_project.name && config.active_project.path) {
            const configPath = config.active_project.path + '/.serena/project.yml';
            html += '<div class="config-value"><span title="Project configuration in ' + configPath + '">' + config.active_project.name + '</span></div>';
        } else {
            html += '<div class="config-value">' + (config.active_project.name || 'None') + '</div>';
        }

        html += '<div class="config-label">Languages:</div>';
        if (this.jetbrainsMode) {
            html += '<div class="config-value">Using JetBrains backend</div>';
        } else {
            html += '<div class="config-value">';
            if (config.languages && config.languages.length > 0) {
                html += '<div class="languages-container">';
                config.languages.forEach(function(language, index) {
                    const isRemovable = config.languages.length > 1;
                    html += '<div class="language-badge' + (isRemovable ? ' removable' : '') + '">';
                    html += language;
                    if (isRemovable) {
                        html += '<span class="language-remove" data-language="' + language + '">&times;</span>';
                    }
                    html += '</div>';
                });
                // Add the "Add Language" button inline with language badges (only if active project exists)
                if (config.active_project && config.active_project.name) {
                    // TODO: address after refactoring, it's not awesome to keep depending on state
                    if (this.isAddingLanguage) {
                        html += '<div id="add-language-spinner" class="language-spinner">';
                    } else {
                        html += '<button id="add-language-btn" class="btn language-add-btn">+ Add Language</button>';
                        html += '<div id="add-language-spinner" class="language-spinner" style="display:none;">';
                    }
                    html += '<div class="spinner"></div>';
                    html += '</div>';
                }
                html += '</div>';
            } else {
                html += 'N/A';
            }
            html += '</div>';
        }

        // Context info
        html += '<div class="config-label">Context:</div>';
        html += '<div class="config-value"><span title="' + config.context.path + '">' + config.context.name + '</span></div>';

        // Modes info
        html += '<div class="config-label">Active Modes:</div>';
        html += '<div class="config-value">';
        if (config.modes.length > 0) {
            const modeSpans = config.modes.map(function(mode) {
                return '<span title="' + mode.path + '">' + mode.name + '</span>';
            });
            html += modeSpans.join(', ');
        } else {
            html += 'None';
        }
        html += '</div>';

        // File Encoding info
        html += '<div class="config-label">File Encoding:</div>';
        html += '<div class="config-value">' + (config.encoding || 'N/A') + '</div>';

        html += '</div>';

        // Active tools - collapsible
        html += '<div style="margin-top: 20px;">';
        html += '<h3 class="collapsible-header" id="tools-header" style="font-size: 16px; margin: 0;">';
        html += '<span>Active Tools (' + config.active_tools.length + ')</span>';
        html += '<span class="toggle-icon' + (wasToolsExpanded ? ' expanded' : '') + '">▼</span>';
        html += '</h3>';
        html += '<div class="collapsible-content tools-grid" id="tools-content" style="' + (wasToolsExpanded ? '' : 'display:none;') + ' margin-top: 10px;">';
        config.active_tools.forEach(function(tool) {
            html += '<div class="tool-item" title="' + tool + '">' + tool + '</div>';
        });
        html += '</div>';
        html += '</div>';

        // Available memories - collapsible (only show if memories exist)
        if (config.available_memories && config.available_memories.length > 0) {
            html += '<div style="margin-top: 20px;">';
            html += '<h3 class="collapsible-header" id="memories-header" style="font-size: 16px; margin: 0;">';
            html += '<span>Available Memories (' + config.available_memories.length + ')</span>';
            html += '<span class="toggle-icon' + (wasMemoriesExpanded ? ' expanded' : '') + '">▼</span>';
            html += '</h3>';
            html += '<div class="collapsible-content memories-container" id="memories-content" style="' + (wasMemoriesExpanded ? '' : 'display:none;') + ' margin-top: 10px;">';
            config.available_memories.forEach(function(memory) {
                html += '<div class="memory-item removable" data-memory="' + memory + '">';
                html += memory;
                html += '<span class="memory-remove" data-memory="' + memory + '">&times;</span>';
                html += '</div>';
            });
            html += '</div>';
            html += '</div>';
        }

        // Configuration help link
        html += '<div style="margin-top: 15px; padding: 10px; background: var(--bg-secondary); border-radius: 4px; font-size: 13px; border: 1px solid var(--border-color);">';
        html += '<span style="color: var(--text-muted);">📖</span> ';
        html += '<a href="https://github.com/oraios/serena#configuration" target="_blank" rel="noopener noreferrer" style="color: var(--btn-primary); text-decoration: none; font-weight: 500;">View Configuration Guide</a>';
        html += '</div>';

        this.$configDisplay.html(html);

        // Attach event handlers for the dynamically created add language button
        $('#add-language-btn').click(this.openLanguageModal.bind(this));

        // Attach event handlers for language remove buttons
        const self = this;
        $('.language-remove').click(function(e) {
            e.preventDefault();
            e.stopPropagation();
            const language = $(this).data('language');
            self.confirmRemoveLanguage(language);
        });

        // Attach event handlers for memory items
        $('.memory-item').click(function(e) {
            e.preventDefault();
            const memoryName = $(this).data('memory');
            self.openEditMemoryModal(memoryName);
        });

        // Attach event handlers for memory remove buttons
        $('.memory-remove').click(function(e) {
            e.preventDefault();
            e.stopPropagation();
            const memoryName = $(this).data('memory');
            self.confirmDeleteMemory(memoryName);
        });

        // Re-attach collapsible handler for the newly created tools header
        $('#tools-header').click(function() {
            const $header = $(this);
            const $content = $('#tools-content');
            const $icon = $header.find('.toggle-icon');

            $content.slideToggle(300);
            $icon.toggleClass('expanded');
        });

        // Re-attach collapsible handler for the newly created memories header
        $('#memories-header').click(function() {
            const $header = $(this);
            const $content = $('#memories-content');
            const $icon = $header.find('.toggle-icon');

            $content.slideToggle(300);
            $icon.toggleClass('expanded');
        });
        } catch (error) {
            console.error('Error in displayConfig:', error);
            this.$configDisplay.html('<div class="error-message">Error displaying configuration: ' + error.message + '</div>');
        }
    }

    displayBasicStats(stats) {
        if (Object.keys(stats).length === 0) {
            this.$basicStatsDisplay.html('<div class="no-stats-message">No tool usage stats collected yet.</div>');
            return;
        }

        // Sort tools by call count (descending)
        const sortedTools = Object.keys(stats).sort((a, b) => {
            return stats[b].num_calls - stats[a].num_calls;
        });

        const maxCalls = Math.max(...sortedTools.map(tool => stats[tool].num_calls));

        let html = '';
        sortedTools.forEach(function(toolName) {
            const count = stats[toolName].num_calls;
            const percentage = maxCalls > 0 ? (count / maxCalls * 100) : 0;

            html += '<div class="stat-bar-container">';
            html += '<div class="stat-tool-name" title="' + toolName + '">' + toolName + '</div>';
            html += '<div class="bar-wrapper">';
            html += '<div class="bar" style="width: ' + percentage + '%"></div>';
            html += '</div>';
            html += '<div class="stat-count">' + count + '</div>';
            html += '</div>';
        });

        this.$basicStatsDisplay.html(html);
    }

    displayProjects(projects) {
        if (!projects || projects.length === 0) {
            this.$projectsDisplay.html('<div class="no-stats-message">No projects registered.</div>');
            return;
        }

        let html = '';
        projects.forEach(function(project) {
            const activeClass = project.is_active ? ' active' : '';
            html += '<div class="project-item' + activeClass + '">';
            html += '<div class="project-name" title="' + project.name + '">' + project.name + '</div>';
            html += '<div class="project-path" title="' + project.path + '">' + project.path + '</div>';
            html += '</div>';
        });

        this.$projectsDisplay.html(html);
    }

    displayAvailableTools(tools) {
        if (!tools || tools.length === 0) {
            this.$availableToolsDisplay.html('<div class="no-stats-message">All tools are active.</div>');
            return;
        }

        let html = '';
        tools.forEach(function(tool) {
            html += '<div class="info-item" title="' + tool.name + '">' + tool.name + '</div>';
        });

        this.$availableToolsDisplay.html(html);
    }

    displayAvailableModes(modes) {
        if (!modes || modes.length === 0) {
            this.$availableModesDisplay.html('<div class="no-stats-message">No modes available.</div>');
            return;
        }

        let html = '';
        modes.forEach(function(mode) {
            const activeClass = mode.is_active ? ' active' : '';
            html += '<div class="info-item' + activeClass + '" title="' + mode.path + '">' + mode.name + '</div>';
        });

        this.$availableModesDisplay.html(html);
    }

    displayAvailableContexts(contexts) {
        if (!contexts || contexts.length === 0) {
            this.$availableContextsDisplay.html('<div class="no-stats-message">No contexts available.</div>');
            return;
        }

        let html = '';
        contexts.forEach(function(context) {
            const activeClass = context.is_active ? ' active' : '';
            html += '<div class="info-item' + activeClass + '" title="' + context.path + '">' + context.name + '</div>';
        });

        this.$availableContextsDisplay.html(html);
    }

    // ===== Logs Methods =====

    displayLogMessage(message) {
        this.$logContainer.append(new LogMessage(message, this.toolNames).$elem);
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

    updateTitle(activeProject) {
        document.title = activeProject ? `${activeProject} – Serena Dashboard` : 'Serena Dashboard';
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

                self.updateTitle(response.active_project);

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

                // Update window title with active project
                self.updateTitle(response.active_project);
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

    // ===== Stats Methods =====

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

    // ===== Theme Methods =====

    initializeTheme() {
        // Check if user has manually set a theme preference
        const savedTheme = localStorage.getItem('serena-theme');

        if (savedTheme) {
            // User has manually set a preference, use it
            this.setTheme(savedTheme);
        } else {
            // No manual preference, detect system color scheme
            this.detectSystemTheme();
        }

        // Listen for system theme changes
        this.setupSystemThemeListener();
    }

    detectSystemTheme() {
        // Check if system prefers dark mode
        const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        const theme = prefersDark ? 'dark' : 'light';
        this.setTheme(theme);
    }

    setupSystemThemeListener() {
        // Listen for changes in system color scheme
        const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');

        const handleSystemThemeChange = (e) => {
            // Only auto-switch if user hasn't manually set a preference
            const savedTheme = localStorage.getItem('serena-theme');
            if (!savedTheme) {
                const newTheme = e.matches ? 'dark' : 'light';
                this.setTheme(newTheme);
            }
        };

        // Add listener for system theme changes
        if (mediaQuery.addEventListener) {
            mediaQuery.addEventListener('change', handleSystemThemeChange);
        } else {
            // Fallback for older browsers
            mediaQuery.addListener(handleSystemThemeChange);
        }
    }

    toggleTheme() {
        const currentTheme = document.documentElement.getAttribute('data-theme') || 'light';
        const newTheme = currentTheme === 'light' ? 'dark' : 'light';

        // When user manually toggles, save their preference
        localStorage.setItem('serena-theme', newTheme);
        this.setTheme(newTheme);
    }

    setTheme(theme) {
        // Set the theme on the document element
        document.documentElement.setAttribute('data-theme', theme);

        // Update the theme toggle button
        if (theme === 'dark') {
            this.$themeIcon.text('☀️');
            this.$themeText.text('Light');
        } else {
            this.$themeIcon.text('🌙');
            this.$themeText.text('Dark');
        }

        // Update the logo based on theme
        this.updateLogo(theme);

        // Save to localStorage
        localStorage.setItem('serena-theme', theme);

        // Update charts if they exist
        this.updateChartsTheme();
    }

    updateLogo(theme) {
        const logoElement = document.getElementById('serena-logo');
        if (logoElement) {
            if (theme === 'dark') {
                logoElement.src = 'serena-logo-dark-mode.svg';
            } else {
                logoElement.src = 'serena-logo.svg';
            }
        }
    }

    updateChartsTheme() {
        const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
        const textColor = isDark ? '#ffffff' : '#000000';
        const gridColor = isDark ? '#444' : '#ddd';

        // Update existing charts if they exist and have the scales property
        if (this.countChart && this.countChart.options.plugins) {
            if (this.countChart.options.plugins.legend) {
                this.countChart.options.plugins.legend.labels.color = textColor;
            }
            this.countChart.update();
        }

        if (this.inputChart && this.inputChart.options.plugins) {
            if (this.inputChart.options.plugins.legend) {
                this.inputChart.options.plugins.legend.labels.color = textColor;
            }
            this.inputChart.update();
        }

        if (this.outputChart && this.outputChart.options.plugins) {
            if (this.outputChart.options.plugins.legend) {
                this.outputChart.options.plugins.legend.labels.color = textColor;
            }
            this.outputChart.update();
        }

        if (this.tokensChart && this.tokensChart.options.scales) {
            this.tokensChart.options.scales.x.ticks.color = textColor;
            this.tokensChart.options.scales.y.ticks.color = textColor;
            this.tokensChart.options.scales.y1.ticks.color = textColor;
            this.tokensChart.options.scales.x.grid.color = gridColor;
            this.tokensChart.options.scales.y.grid.color = gridColor;
            this.tokensChart.options.scales.y1.grid.color = gridColor;
            this.tokensChart.options.scales.y.title.color = textColor;
            this.tokensChart.options.scales.y1.title.color = textColor;
            if (this.tokensChart.options.plugins && this.tokensChart.options.plugins.legend) {
                this.tokensChart.options.plugins.legend.labels.color = textColor;
            }
            this.tokensChart.update();
        }
    }

    // ===== Language Management Methods =====

    confirmRemoveLanguage(language) {
        // Store the language to remove
        this.languageToRemove = language;

        // Set language name in modal
        this.$removeLanguageName.text(language);

        // Show modal
        this.$removeLanguageModal.fadeIn(200);
    }

    closeRemoveLanguageModal() {
        this.$removeLanguageModal.fadeOut(200);
        this.languageToRemove = null;
    }

    confirmRemoveLanguageOk() {
        if (this.languageToRemove) {
            this.removeLanguage(this.languageToRemove);
            this.closeRemoveLanguageModal();
        }
    }

    removeLanguage(language) {
        const self = this;

        $.ajax({
            url: '/remove_language',
            type: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({
                language: language
            }),
            success: function(response) {
                if (response.status === 'success') {
                    // Reload config to show updated language list
                    self.loadConfigOverview();
                } else {
                    alert('Error: ' + response.message);
                }
            },
            error: function(xhr, status, error) {
                console.error('Error removing language:', error);
                alert('Error removing language: ' + (xhr.responseJSON ? xhr.responseJSON.message : error));
            }
        });
    }

    openLanguageModal() {
        // Set project name in modal
        this.$modalProjectName.text(this.activeProjectName || 'Unknown');

        // Load available languages into modal dropdown
        this.loadAvailableLanguages();

        // Show modal
        this.$addLanguageModal.fadeIn(200);
    }

    closeLanguageModal() {
        this.$addLanguageModal.fadeOut(200);
        this.$modalLanguageSelect.empty();
        this.$modalAddBtn.prop('disabled', false).text('Add Language');
    }

    loadAvailableLanguages() {
        let self = this;
        $.ajax({
            url: '/get_available_languages',
            type: 'GET',
            success: function(response) {
                const languages = response.languages || [];
                // Clear all existing options
                self.$modalLanguageSelect.empty();

                if (languages.length === 0) {
                    // Show message if no languages available
                    self.$modalLanguageSelect.append($('<option>').val('').text('No languages available to add'));
                    self.$modalAddBtn.prop('disabled', true);
                } else {
                    // Add language options
                    languages.forEach(function(language) {
                        self.$modalLanguageSelect.append($('<option>').val(language).text(language));
                    });
                    self.$modalAddBtn.prop('disabled', false);
                }
            },
            error: function(xhr, status, error) {
                console.error('Error loading available languages:', error);
            }
        });
    }

    addLanguageFromModal() {
        const selectedLanguage = this.$modalLanguageSelect.val();
        if (!selectedLanguage) {
            alert('No language selected or no languages available to add');
            return;
        }

        const self = this;

        // Close modal immediately
        self.closeLanguageModal();

        // Hide the inline add language button and show spinner
        $('#add-language-btn').hide();
        $('#add-language-spinner').show();
        self.isAddingLanguage = true;

        $.ajax({
            url: '/add_language',
            type: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({
                language: selectedLanguage
            }),
            success: function(response) {
                if (response.status === 'success') {
                    console.log("Language added successfully");
                } else {
                    alert('Error: ' + response.message);
                    // Restore button visibility on error
                    $('#add-language-btn').show();
                    $('#add-language-spinner').hide();
                }
            },
            error: function(xhr, status, error) {
                console.error('Error adding language:', error);
                alert('Error adding language: ' + (xhr.responseJSON ? xhr.responseJSON.message : error));
                // Restore button visibility on error
                $('#add-language-btn').show();
                $('#add-language-spinner').hide();
            },
            complete: function() {
                self.isAddingLanguage = false;
                self.loadConfigOverview();
            }
        });
    }

    // ===== Memory Editing Methods =====

    openEditMemoryModal(memoryName) {
        const self = this;
        this.currentMemoryName = memoryName;
        this.memoryContentDirty = false;

        // Set memory name in modal
        this.$editMemoryName.text(memoryName);

        // Load memory content
        $.ajax({
            url: '/get_memory',
            type: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({
                memory_name: memoryName
            }),
            success: function(response) {
                if (response.status === 'error') {
                    alert('Error: ' + response.message);
                    return;
                }
                self.originalMemoryContent = response.content;
                self.$editMemoryContent.val(response.content);
                self.memoryContentDirty = false;
                self.$editMemoryModal.fadeIn(200);
            },
            error: function(xhr, status, error) {
                console.error('Error loading memory:', error);
                alert('Error loading memory: ' + (xhr.responseJSON ? xhr.responseJSON.message : error));
            }
        });
    }

    closeEditMemoryModal() {
        // Check if there are unsaved changes
        if (this.memoryContentDirty) {
            if (!confirm('You have unsaved changes. Are you sure you want to close?')) {
                return;
            }
        }

        this.$editMemoryModal.fadeOut(200);
        this.currentMemoryName = null;
        this.originalMemoryContent = null;
        this.memoryContentDirty = false;
    }

    trackMemoryChanges() {
        const currentContent = this.$editMemoryContent.val();
        this.memoryContentDirty = (currentContent !== this.originalMemoryContent);
    }

    saveMemoryFromModal() {
        const self = this;
        const memoryName = this.currentMemoryName;
        const content = this.$editMemoryContent.val();

        if (!memoryName) {
            alert('No memory selected');
            return;
        }

        // Disable button during request
        self.$editMemorySaveBtn.prop('disabled', true).text('Saving...');

        $.ajax({
            url: '/save_memory',
            type: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({
                memory_name: memoryName,
                content: content
            }),
            success: function(response) {
                if (response.status === 'success') {
                    // Update original content and reset dirty flag
                    self.originalMemoryContent = content;
                    self.memoryContentDirty = false;
                    // Close modal
                    self.$editMemoryModal.fadeOut(200);
                    self.currentMemoryName = null;
                } else {
                    alert('Error: ' + response.message);
                }
            },
            error: function(xhr, status, error) {
                console.error('Error saving memory:', error);
                alert('Error saving memory: ' + (xhr.responseJSON ? xhr.responseJSON.message : error));
            },
            complete: function() {
                // Re-enable button
                self.$editMemorySaveBtn.prop('disabled', false).text('Save');
            }
        });
    }

    confirmDeleteMemory(memoryName) {
        // Set memory name to delete
        this.memoryToDelete = memoryName;

        // Set memory name in modal
        this.$deleteMemoryName.text(memoryName);

        // Show modal
        this.$deleteMemoryModal.fadeIn(200);
    }

    closeDeleteMemoryModal() {
        this.$deleteMemoryModal.fadeOut(200);
        this.memoryToDelete = null;
    }

    confirmDeleteMemoryOk() {
        if (this.memoryToDelete) {
            this.deleteMemory(this.memoryToDelete);
            this.closeDeleteMemoryModal();
        }
    }

    deleteMemory(memoryName) {
        const self = this;

        $.ajax({
            url: '/delete_memory',
            type: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({
                memory_name: memoryName
            }),
            success: function(response) {
                if (response.status === 'success') {
                    // Reload config to show updated memory list
                    self.loadConfigOverview();
                } else {
                    alert('Error: ' + response.message);
                }
            },
            error: function(xhr, status, error) {
                console.error('Error deleting memory:', error);
                alert('Error deleting memory: ' + (xhr.responseJSON ? xhr.responseJSON.message : error));
            }
        });
    }

    // ===== Shutdown Method =====

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

        // Close menu
        self.$menuDropdown.hide();
    }
}
