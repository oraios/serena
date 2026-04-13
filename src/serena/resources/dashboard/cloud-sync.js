/*
 * Serena Cloud Sync dashboard panel.
 *
 * Contract with the server (see serena/cloud_sync/dashboard_routes.py):
 *   GET  /api/cloud-sync/config   -> masked settings ({ ****abcd })
 *   POST /api/cloud-sync/config   -> accepts partial updates; "****" means unchanged
 *   POST /api/cloud-sync/test     -> round-trip probe
 *   GET  /api/cloud-sync/status   -> inventory counts + plan counts
 *   POST /api/cloud-sync/push     -> dry_run defaults to true (dry-run-first UX)
 *   POST /api/cloud-sync/pull     -> same
 */

"use strict";

(function () {
    const $ = window.jQuery;

    // Per-process token for defense-in-depth against other local processes.
    // Fetched once on load and attached to every mutating request.
    let CLOUD_SYNC_TOKEN = null;

    function withToken(settings) {
        settings = settings || {};
        settings.headers = Object.assign({}, settings.headers, {
            "X-Cloud-Sync-Token": CLOUD_SYNC_TOKEN || "",
        });
        return settings;
    }

    // Patch $.ajax so every cloud-sync call carries the token.
    const originalAjax = $.ajax;
    $.ajax = function (urlOrSettings, settings) {
        if (typeof urlOrSettings === "string") {
            settings = settings || {};
            settings.url = urlOrSettings;
        } else {
            settings = urlOrSettings || {};
        }
        if ((settings.url || "").indexOf("/api/cloud-sync/") === 0 &&
            (settings.url || "").indexOf("/api/cloud-sync/bootstrap-token") !== 0) {
            settings = withToken(settings);
        }
        return originalAjax.call(this, settings);
    };

    function fetchToken() {
        return originalAjax({
            url: "/api/cloud-sync/bootstrap-token",
            method: "GET",
        }).done(function (d) {
            CLOUD_SYNC_TOKEN = d && d.token;
        });
    }

    const secretFields = new Set([
        "R2_SECRET_ACCESS_KEY",
        "AWS_SECRET_ACCESS_KEY",
        "AZURE_STORAGE_ACCOUNT_KEY",
    ]);

    function showProvider(provider) {
        $(".cs-provider-r2, .cs-provider-s3, .cs-provider-azure").attr("hidden", true);
        $(`.cs-provider-${provider}`).removeAttr("hidden");
    }

    function loadConfig() {
        return $.get("/api/cloud-sync/config").done(function (d) {
            if (d.env_path) $("#cs-env-path").text(d.env_path + " (chmod 600)");
            if (!d.configured) {
                showProvider($("#cs-provider").val() || "r2");
                return;
            }
            const s = d.settings || {};
            $("#cs-provider").val(s.provider || "r2");
            $("#cs-root-prefix").val(s.root_prefix || "serena-sync/");
            if (s.r2) {
                $("#cs-r2-account").val(s.r2.account_id || "");
                $("#cs-r2-akid").val(s.r2.access_key_id || "");
                $("#cs-r2-secret").val(s.r2.secret_access_key || "");
                $("#cs-r2-bucket").val(s.r2.bucket || "");
                $("#cs-r2-endpoint").val(s.r2.endpoint_url || "");
            }
            if (s.s3) {
                $("#cs-s3-akid").val(s.s3.access_key_id || "");
                $("#cs-s3-secret").val(s.s3.secret_access_key || "");
                $("#cs-s3-bucket").val(s.s3.bucket || "");
                $("#cs-s3-region").val(s.s3.region || "us-east-1");
                $("#cs-s3-endpoint").val(s.s3.endpoint_url || "");
            }
            if (s.azure) {
                $("#cs-az-account").val(s.azure.account_name || "");
                $("#cs-az-key").val(s.azure.account_key || "");
                $("#cs-az-container").val(s.azure.container || "");
                $("#cs-az-suffix").val(s.azure.endpoint_suffix || "core.windows.net");
            }
            showProvider(s.provider || "r2");
        });
    }

    function collectPayload() {
        const payload = {
            CLOUD_SYNC_PROVIDER: $("#cs-provider").val(),
            CLOUD_SYNC_ROOT_PREFIX: $("#cs-root-prefix").val() || "serena-sync/",
        };
        function addField(key, val) {
            if (val === undefined || val === null) return;
            payload[key] = val;
        }
        addField("R2_ACCOUNT_ID", $("#cs-r2-account").val());
        addField("R2_ACCESS_KEY_ID", $("#cs-r2-akid").val());
        addField("R2_SECRET_ACCESS_KEY", $("#cs-r2-secret").val());
        addField("R2_BUCKET", $("#cs-r2-bucket").val());
        addField("R2_ENDPOINT_URL", $("#cs-r2-endpoint").val());
        addField("AWS_ACCESS_KEY_ID", $("#cs-s3-akid").val());
        addField("AWS_SECRET_ACCESS_KEY", $("#cs-s3-secret").val());
        addField("AWS_BUCKET", $("#cs-s3-bucket").val());
        addField("AWS_REGION", $("#cs-s3-region").val());
        addField("AWS_ENDPOINT_URL", $("#cs-s3-endpoint").val());
        addField("AZURE_STORAGE_ACCOUNT", $("#cs-az-account").val());
        addField("AZURE_STORAGE_ACCOUNT_KEY", $("#cs-az-key").val());
        addField("AZURE_CONTAINER", $("#cs-az-container").val());
        addField("AZURE_ENDPOINT_SUFFIX", $("#cs-az-suffix").val());
        return payload;
    }

    function doSave() {
        const payload = collectPayload();
        return $.ajax({
            url: "/api/cloud-sync/config",
            method: "POST",
            contentType: "application/json",
            data: JSON.stringify(payload),
        });
    }

    function renderStatus(data) {
        const c = data.plan_counts || {};
        const html = ["upload", "download", "skip", "conflict"].map(function (k) {
            return `<div class="card">
                <div class="label">${k}</div>
                <div class="value">${c[k] || 0}</div>
            </div>`;
        }).join("") + `
            <div class="card">
                <div class="label">local</div>
                <div class="value">${data.local_count ?? 0}</div>
            </div>
            <div class="card">
                <div class="label">remote</div>
                <div class="value">${data.remote_count ?? 0}</div>
            </div>`;
        $("#cs-status-cards").html(html);
    }

    function refreshStatus() {
        const params = {};
        if ($("#cs-include-local-yml").is(":checked")) {
            params["include_project_local_yml"] = "1";
        }
        return $.get("/api/cloud-sync/status", params).done(renderStatus);
    }

    function doRun(mode, dryRun) {
        const body = {
            dry_run: !!dryRun,
            byte_compare: $("#cs-byte-compare").is(":checked"),
            include_project_local_yml: $("#cs-include-local-yml").is(":checked"),
        };
        $("#cs-plan-output").text(`Running ${mode}${dryRun ? " (dry-run)" : ""}...`);
        return $.ajax({
            url: "/api/cloud-sync/" + mode,
            method: "POST",
            contentType: "application/json",
            data: JSON.stringify(body),
        }).done(function (d) {
            $("#cs-plan-output").text(JSON.stringify(d, null, 2));
            refreshStatus();
        }).fail(function (xhr) {
            $("#cs-plan-output").text("ERROR " + xhr.status + "\n" + (xhr.responseText || ""));
        });
    }

    $(function () {
        $("#cs-provider").on("change", function () {
            showProvider($(this).val());
        });

        $("#cs-save").on("click", function () {
            doSave().done(function () {
                $("#cs-plan-output").text("Saved. Reloading config...");
                loadConfig();
            }).fail(function (xhr) {
                $("#cs-plan-output").text("Save failed: " + xhr.status + " " + xhr.responseText);
            });
        });

        $("#cs-test").on("click", function () {
            $("#cs-plan-output").text("Testing connection...");
            $.post("/api/cloud-sync/test").done(function (d) {
                $("#cs-plan-output").text("Test " + (d.ok ? "OK" : "FAILED") + "\n" + JSON.stringify(d, null, 2));
            }).fail(function (xhr) {
                $("#cs-plan-output").text("Test error: " + xhr.status + "\n" + xhr.responseText);
            });
        });

        $("#cs-plan-push").on("click", function () { doRun("push", true); });
        $("#cs-plan-pull").on("click", function () { doRun("pull", true); });
        $("#cs-push").on("click", function () {
            if (confirm("Push now? Divergent remote files are preserved (never overwritten).")) doRun("push", false);
        });
        $("#cs-pull").on("click", function () {
            if (confirm("Pull now? Divergent local files are preserved as .cloud-<ts> siblings.")) doRun("pull", false);
        });
        $("#cs-include-local-yml").on("change", refreshStatus);

        fetchToken().always(function () {
            loadConfig().always(refreshStatus);
        });
    });
})();
