/* Navigation behavior for the Serena docs theme.

   1. The sidebar tree starts minimized; every expand/collapse the reader performs
      persists across pages (localStorage), in both directions, until changed again.
   2. The mobile navigation drawer stays open across pages until the reader closes
      it (sessionStorage), and is restored before the first paint so that following
      a link does not make it slide shut and open again. */

(function () {
    "use strict";

    var NAV_KEY = "serena-docs-nav";
    var DRAWER_KEY = "serena-docs-drawer";
    var DRAWER_OPEN_CLASS = "serena-drawer-open";
    var DRAWER_RESTORING_CLASS = "serena-drawer-restoring";

    /* Resolve each store once. Reading window.localStorage is itself enough to throw
       where storage is blocked (cookies disabled, sandboxed origins), so the access
       has to happen inside the guard rather than at the call site. */
    function openStorage(name) {
        try {
            var store = window[name];
            store.setItem("__serena_probe__", "1");
            store.removeItem("__serena_probe__");
            return store;
        } catch (e) {
            /* storage unavailable: fall back to the theme's stock behavior */
            return null;
        }
    }

    var navStore = openStorage("localStorage");
    var drawerStore = openStorage("sessionStorage");

    function readStorage(store, key) {
        if (!store) {
            return null;
        }
        try {
            return store.getItem(key);
        } catch (e) {
            return null;
        }
    }

    function writeStorage(store, key, value) {
        if (!store) {
            return;
        }
        try {
            store.setItem(key, value);
        } catch (e) {
            /* ignore */
        }
    }

    /* Bootstrap keeps one tooltip instance per element, and hiding through it clears
       the shown state properly, which deleting the node would not. Silent wherever
       Bootstrap has not loaded or has not yet claimed the element. */
    function dismissTooltip(element) {
        var bootstrap = window.bootstrap;

        if (!bootstrap || !bootstrap.Tooltip || !bootstrap.Tooltip.getInstance) {
            return;
        }

        var instance = bootstrap.Tooltip.getInstance(element);
        if (instance) {
            instance.hide();
        }
    }

    /* The theme's own head script writes an empty colour-scheme mode when the reader
       has no stored preference, and its validator then rejects that value and logs an
       error on every first visit. Naming the default it would fall back to anyway
       keeps the console clean. */
    if (!document.documentElement.dataset.mode) {
        document.documentElement.dataset.mode = "auto";
    }

    /* The drawer is a phone-width concept: below this width the sidebar is a panel the
       reader opens and closes, above it the sidebar is always a column.

       The distinction has to be enforced, because #pst-primary-sidebar-checkbox is one
       element whose meaning is redefined by width: sphinx-book-theme reads :checked as
       "hide the sidebar" from 992px up, the inverse of the drawer. Restoring a drawer
       state above the breakpoint therefore asks the theme to hide a sidebar the reader
       cannot bring back, since the button that would reveal it is hidden at those
       widths. */
    var DRAWER_MEDIA = "(max-width: 767.98px)";

    function drawerApplies() {
        return !window.matchMedia || window.matchMedia(DRAWER_MEDIA).matches;
    }

    /* Restore the drawer before the document body is parsed: the class applies the
       open state at first paint, so no transition runs on arrival. */
    if (drawerApplies() && readStorage(drawerStore, DRAWER_KEY) === "open") {
        document.documentElement.classList.add(DRAWER_OPEN_CLASS);
        document.documentElement.classList.add(DRAWER_RESTORING_CLASS);
    }

    /* Fetch pages before they are asked for, so following a link renders from memory
       rather than from the network. Chromium implements this declaratively through
       speculation rules ("moderate" starts on hover/touch, not on sight); elsewhere the
       same effect comes from injecting a prefetch link on first hover. */
    /* The documentation root, which is not the server root when the site is published
       under a path (e.g. /serena/). Derived from this script's own URL, since static
       assets always resolve to <root>/_static/. */
    function documentationRoot() {
        var script = document.querySelector('script[src*="serena-docs.js"]');

        if (script) {
            var path = new URL(script.src, window.location.href).pathname;
            var marker = path.lastIndexOf("/_static/");
            if (marker >= 0) {
                return path.slice(0, marker + 1);
            }
        }

        return new URL(".", window.location.href).pathname;
    }

    /* The two pages a reader is most likely to open next are named at the foot of the
       one they are on. Everything else is a guess; these two are an answer. */
    function neighbouringPages() {
        var here = window.location.href.split("#")[0];
        var urls = [];

        document.querySelectorAll(".prev-next-footer a[href]").forEach(function (link) {
            var href = link.href.split("#")[0];

            if (link.origin === window.location.origin && href !== here && urls.indexOf(href) < 0) {
                urls.push(href);
            }
        });

        return urls;
    }

    function enablePrefetching() {
        var scope = documentationRoot();

        /* A reader who has asked their connection to be spared should not have pages
           fetched on their behalf that they may never open. */
        var connection = navigator.connection;
        if (connection && connection.saveData) {
            return;
        }

        if (
            window.HTMLScriptElement &&
            HTMLScriptElement.supports &&
            HTMLScriptElement.supports("speculationrules")
        ) {
            var speculation = {
                prefetch: [
                    {
                        source: "document",
                        where: { href_matches: scope + "*" },
                        eagerness: "moderate",
                    },
                ],
            };

            /* Previous and next are prerendered outright rather than merely fetched:
               the page is built in the background, so following either one displays a
               document that is already laid out instead of starting to build one. Two
               is also the most the browser will prerender from a rule set, which the
               pair happens to fit exactly. */
            var neighbours = neighbouringPages();
            if (neighbours.length) {
                speculation.prerender = [{ urls: neighbours, eagerness: "immediate" }];
            }

            var rules = document.createElement("script");
            rules.type = "speculationrules";
            rules.textContent = JSON.stringify(speculation);
            document.head.appendChild(rules);
            return;
        }

        var prefetched = {};

        function prefetch(event) {
            var link = event.target.closest ? event.target.closest("a[href]") : null;
            if (!link || link.origin !== window.location.origin) {
                return;
            }

            var href = link.href.split("#")[0];
            if (prefetched[href] || href === window.location.href.split("#")[0]) {
                return;
            }
            prefetched[href] = true;

            var hint = document.createElement("link");
            hint.rel = "prefetch";
            hint.href = href;
            document.head.appendChild(hint);
        }

        document.addEventListener("mouseover", prefetch, { passive: true });
        document.addEventListener("touchstart", prefetch, { passive: true });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", enablePrefetching);
    } else {
        enablePrefetching();
    }

    function navState() {
        try {
            return JSON.parse(readStorage(navStore, NAV_KEY)) || {};
        } catch (e) {
            return {};
        }
    }

    /* A section row carries two things that a reader wants separately: the section's own
       page, and the list of what is inside it. They get one target each.

       The chevron opens and closes the section and never navigates, so any section can be
       looked into from wherever the reader happens to be. The title is an ordinary link to
       the section's page; following it lands on a page that renders its own section open,
       so the section ends up expanded either way.

       The theme ships the title as a link and the chevron as decoration inside the summary,
       which makes the whole row toggle. Keeping the link but stopping its click from
       reaching the summary is what separates them. */
    function makeSectionAnExpander(item) {
        var link = item.querySelector(":scope > a");
        var details = item.querySelector(":scope > details");
        if (!link || !details) {
            return;
        }

        var summary = details.querySelector(":scope > summary");
        if (!summary) {
            return;
        }

        /* The theme already emits the title as a sibling of the disclosure rather than
           inside it, which is exactly the structure this needs: two controls side by side
           rather than one inside the other. Moving the link into the summary would put a
           link inside a control that is itself interactive — nested interactive controls,
           which leaves a screen reader describing one thing and operating another.

           So the link stays where it is and only gains a class; the stylesheet lifts the
           chevron onto the same row. Nothing has to stop the link from toggling, because
           it was never inside the thing that toggles. */
        link.classList.add("serena-section-label");
        summary.classList.add("serena-section-toggle");

        /* With the title outside it, the summary holds only a chevron and has nothing to
           be called. It is the control that opens this particular section, so it is named
           for the section — otherwise a reader hears "disclosure triangle, collapsed" and
           has to guess which of the five it belongs to. */
        summary.setAttribute("aria-label", link.textContent.trim());
    }

    /* A stable identity for a collapsible section: the path of labels leading to it,
       e.g. "Evaluation/Prompts". Hrefs cannot be used, because the entry for the page
       currently being viewed is rendered as href="#". */
    function sectionKey(item) {
        var labels = [];
        var node = item;

        while (node && !node.classList.contains("bd-sidebar-primary")) {
            if (node.tagName === "LI") {
                var label =
                    node.querySelector(":scope > details > summary > .serena-section-label") ||
                    node.querySelector(":scope > a");
                if (label) {
                    labels.unshift(label.textContent.trim());
                }
            }
            node = node.parentElement;
        }

        return labels.join("/");
    }

    function restoreNav(sidebar) {
        var state = navState();

        sidebar.querySelectorAll("li.has-children").forEach(makeSectionAnExpander);

        /* Which page you are on is drawn as a colour and a rule down the left edge of its
           title, and is otherwise unsaid: Sphinx marks the anchor with a class and emits
           no `aria-current`, so a reader who is not looking at the tree is told nothing.
           Mark the one anchor carrying that class — the same element the rule is drawn
           against, so what is shown and what is announced cannot drift apart. */
        var here = sidebar.querySelector(".bd-links a.current");
        if (here) {
            here.setAttribute("aria-current", "page");
        }

        sidebar
            .querySelectorAll("li.has-children > details")
            .forEach(function (details) {
                var key = sectionKey(details.parentElement);

                /* Sections the page itself renders open, and those opened here while
                   restoring, emit a toggle of their own; ignore that first one so only
                   the reader's choices are recorded. */
                var settling = true;
                window.setTimeout(function () {
                    settling = false;
                }, 0);

                /* The section holding the page being read is always open. A reader who
                   collapsed it earlier and has now followed a link into it has said the
                   more recent thing, and arriving inside a section that shows none of
                   its contents reads as the tree having lost its place. */
                if (details.parentElement.classList.contains("current")) {
                    details.open = true;
                } else if (Object.prototype.hasOwnProperty.call(state, key)) {
                    details.open = state[key];
                }

                details.addEventListener("toggle", function () {
                    if (settling) {
                        return;
                    }
                    var current = navState();
                    current[key] = details.open;
                    writeStorage(navStore, NAV_KEY, JSON.stringify(current));
                });
            });
    }

    /* This script runs from <head>, so the sidebar and its <details> elements do not
       exist yet; wait for the parsed document. (An element matches a selector as soon
       as its opening tag is parsed, so probing for the sidebar earlier would find it
       empty: nothing would be restored and no listeners would be attached.) */
    function whenSidebarReady(callback) {
        function run() {
            var sidebar = document.querySelector(".bd-sidebar-primary");
            if (sidebar) {
                callback(sidebar);
            }
        }

        if (document.readyState === "loading") {
            document.addEventListener("DOMContentLoaded", run);
        } else {
            run();
        }
    }

    whenSidebarReady(restoreNav);

    document.addEventListener("DOMContentLoaded", function () {
        /* The theme's ".md" item is an ordinary link to the page's source, so following
           it displays the file rather than saving it — servers send Markdown as text,
           and the anchor asks for nothing else — in a new tab that then just sits there.
           The download attribute is what makes it a download, and it is honoured because
           _sources is same-origin wherever the site is served from. */
        document
            .querySelectorAll("a.btn-download-source-button")
            .forEach(function (link) {
                link.setAttribute("download", "");
                link.removeAttribute("target");
            });

        /* A link that leaves the site opens in a new tab: these docs are a working
           reference, and a reader mid-setup who follows a GitHub link should keep
           their place here. Done at load rather than at build time because only .md
           content passes through MyST — the generated reference's links and the
           theme's own chrome never see its links_external_new_tab option. Origin is
           the test, so same-site links (and the download button above, which is
           same-origin) are never touched; an explicit target set by an author wins.
           noopener, so the opened page holds no handle back into this one. */
        document.querySelectorAll("a[href]").forEach(function (a) {
            if (
                (a.protocol === "http:" || a.protocol === "https:") &&
                a.origin !== window.location.origin &&
                !a.hasAttribute("target")
            ) {
                a.setAttribute("target", "_blank");
                var rel = a.getAttribute("rel");
                a.setAttribute("rel", rel ? rel + " noopener" : "noopener");
            }
        });

        /* The drawer is a pure-CSS checkbox in the theme; keep it in sync with the
           restored state, then hand control back to the theme's own rules. */
        var checkbox = document.getElementById("pst-primary-sidebar-checkbox");
        if (!checkbox) {
            return;
        }

        /* What the checkbox means depends on the width, and crossing the breakpoint by
           resizing or rotating fires no event of its own — so the state is re-applied on
           every crossing rather than only on load. Storage is read here, never written:
           it records what the reader chose at drawer width, and returning to that width
           restores it. */
        function applyWidth() {
            var open =
                drawerApplies() && readStorage(drawerStore, DRAWER_KEY) === "open";

            checkbox.checked = open;
            document.documentElement.classList.toggle(DRAWER_OPEN_CLASS, open);
        }

        applyWidth();

        if (window.matchMedia) {
            var drawerQuery = window.matchMedia(DRAWER_MEDIA);

            if (drawerQuery.addEventListener) {
                drawerQuery.addEventListener("change", applyWidth);
            } else if (drawerQuery.addListener) {
                /* Safari below 14 */
                drawerQuery.addListener(applyWidth);
            }
        }

        /* the open state stays expressed as a class (it also drives the toggle
           button's icon); only the suppressed transition is a one-off */
        window.requestAnimationFrame(function () {
            document.documentElement.classList.remove(DRAWER_RESTORING_CLASS);
        });

        function remember() {
            /* deferred: the theme's own click handler assigns checkbox.checked, so
               read the state after it has run */
            window.setTimeout(function () {
                document.documentElement.classList.toggle(
                    DRAWER_OPEN_CLASS,
                    checkbox.checked
                );
                /* Only drawer widths have a drawer to remember: above the breakpoint
                   the checkbox is the theme's hide control and says nothing about what
                   the reader wants on a phone. */
                if (drawerApplies()) {
                    writeStorage(
                        drawerStore,
                        DRAWER_KEY,
                        checkbox.checked ? "open" : "closed"
                    );
                }
            }, 0);
        }

        /* Nothing ever dispatches "change" at this checkbox: it is display: none, the
           backdrop that would toggle it is hidden at every width, and everything that
           moves it — the toggle button, and the theme's own Escape handler — assigns
           .checked from script, which fires no event. So the two ways it actually
           moves are each observed directly. */
        document.querySelectorAll(".primary-toggle").forEach(function (button) {
            button.addEventListener("click", remember);

            /* This button carries no tooltip. A tooltip raised by a tap has nothing to
               dismiss it — there is no pointer to move away — so it sits over the header
               until the reader touches something else, and hiding it on click does not
               help, because the pointer is still on the button and Bootstrap shows it
               again. The button is hidden above the drawer width anyway, so the tooltip
               could only ever appear where it is a nuisance. The accessible name stays. */
            /* Its name lives in the title attribute, which Bootstrap moves to
               data-bs-original-title when it builds the tooltip — and that is not a
               source of an accessible name. Taking the tooltip away would leave the
               button nameless, so the name is written where it will survive. */
            var name =
                button.getAttribute("aria-label") ||
                button.getAttribute("title") ||
                button.getAttribute("data-bs-original-title");

            if (name) {
                button.setAttribute("aria-label", name);
            }

            dismissTooltip(button);
            button.removeAttribute("data-bs-toggle");
        });

        /* Escape, pressed inside the panel, is the theme's way of closing the drawer.
           It only unchecks the checkbox, so without this the class kept here would go
           on holding the panel open — visibly, since that class carries !important —
           and the stored state would say "open" for a drawer the reader just shut. */
        var sidebar = document.querySelector(".bd-sidebar-primary");
        if (sidebar) {
            sidebar.addEventListener("keydown", function (event) {
                if (event.key === "Escape") {
                    remember();
                }
            });
        }

        /* The theme cycles the colour-scheme button in a different order depending on
           the operating system's own setting (auto → light → dark on a dark desktop,
           auto → dark → light on a light one), so the same button behaves differently
           from machine to machine and the icon sequence never becomes familiar. The
           three states are kept, in one fixed order, on every machine. Intercepted in
           the capture phase, which is what keeps the theme's own handler from running. */
        var MODES = ["auto", "light", "dark"];

        /* The theme names this button "light/dark" whatever it is currently set to, so
           a reader who cannot see the icon is told the same thing in all three states
           and learns nothing about what pressing it will do. The name is kept in step
           with the state instead. Bootstrap moves a title into data-bs-original-title
           when it builds the tooltip, so whichever one is in play is the one updated. */
        var MODE_LABELS = {
            auto: "Color scheme: system default. Activate for light.",
            light: "Color scheme: light. Activate for dark.",
            dark: "Color scheme: dark. Activate for system default.",
        };

        /* The tooltip is read by people who can already see the icon, so it names the
           state and stops; the sentence above is for a reader who cannot, and says what
           pressing the button will do. They are set separately because Bootstrap takes
           the title attribute over for the tooltip, and one string cannot be both terse
           and instructive. */
        var MODE_TOOLTIPS = {
            auto: "Color scheme: system default",
            light: "Color scheme: light",
            dark: "Color scheme: dark",
        };

        function nameThemeButtons(mode) {
            var label = MODE_LABELS[mode] || MODE_LABELS.auto;
            var tooltip = MODE_TOOLTIPS[mode] || MODE_TOOLTIPS.auto;

            document.querySelectorAll(".theme-switch-button").forEach(function (button) {
                button.setAttribute("aria-label", label);

                if (button.hasAttribute("data-bs-original-title")) {
                    button.setAttribute("data-bs-original-title", tooltip);
                } else {
                    button.setAttribute("title", tooltip);
                }

                dismissTooltip(button);
            });
        }

        nameThemeButtons(document.documentElement.dataset.mode);

        document.addEventListener(
            "click",
            function (event) {
                var button = event.target.closest
                    ? event.target.closest(".theme-switch-button")
                    : null;
                if (!button) {
                    return;
                }

                event.preventDefault();
                event.stopPropagation();

                var current = MODES.indexOf(document.documentElement.dataset.mode);
                var next = MODES[(current + 1) % MODES.length];
                var systemPrefersDark = window.matchMedia(
                    "(prefers-color-scheme: dark)"
                ).matches;

                document.documentElement.dataset.mode = next;
                document.documentElement.dataset.theme =
                    next === "auto" ? (systemPrefersDark ? "dark" : "light") : next;

                writeStorage(navStore, "mode", next);
                writeStorage(navStore, "theme", document.documentElement.dataset.theme);

                nameThemeButtons(next);

                document.querySelectorAll(".dropdown-menu").forEach(function (menu) {
                    menu.classList.toggle(
                        "dropdown-menu-dark",
                        document.documentElement.dataset.theme === "dark"
                    );
                });
            },
            true
        );

        /* "Back to top" is shown by the theme only while the reader is scrolling
           upwards, which is the one moment it is least needed — scrolling up is itself
           a way back. Show it whenever the page has been scrolled past the header,
           regardless of direction. The theme's own handler is loaded after this file
           and keeps assigning the button's inline display, so visibility is expressed
           as a class that the stylesheet resolves instead. */
        var backToTop = document.getElementById("pst-back-to-top");
        if (backToTop) {
            var header = document.querySelector(".bd-header");
            var threshold = header ? header.getBoundingClientRect().height : 0;

            var showBackToTop = function () {
                backToTop.classList.toggle("serena-visible", window.scrollY > threshold);
            };

            window.addEventListener("scroll", showBackToTop, { passive: true });
            showBackToTop();
        }

    });

    /* The Contents rail, rebuilt on demand. The stock right rail repeated on-screen
       headings and reserved width whether or not it had anything to say; this is its
       replacement: a pill that costs the article nothing and expands into the page's
       heading tree only when asked. It renders solely where navigation earns its place —
       five or more section headings — so short pages stay clean. The current section is
       marked as the reader moves, because "where am I" is half of why anyone opens a
       table of contents. */
    document.addEventListener("DOMContentLoaded", function () {
        /* sphinx hangs the ids on the section wrappers, not the headings — so the
           anchors come from each heading's parent section */
        var headings = Array.prototype.slice.call(
            document.querySelectorAll(".bd-article section[id] > h2, .bd-article section[id] > h3")
        );
        if (headings.length < 5) {
            return;
        }

        var button = document.createElement("button");
        button.className = "serena-toc-btn";
        button.setAttribute("aria-expanded", "false");
        button.innerHTML = '<span aria-hidden="true">☰</span> On this page';

        var panel = document.createElement("nav");
        panel.className = "serena-toc-panel";
        panel.setAttribute("aria-label", "On this page");
        panel.hidden = true;

        var title = document.createElement("div");
        title.className = "serena-toc-title";
        title.textContent = "On this page";
        panel.appendChild(title);

        /* headings end in the theme's headerlink anchor ("#"); the entry wants the text alone */
        var links = headings.map(function (h) {
            var a = document.createElement("a");
            a.href = "#" + h.parentElement.id;
            a.className = h.tagName === "H3" ? "l3" : "l2";
            a.textContent = h.textContent.replace(/#\s*$/, "").trim();
            panel.appendChild(a);
            return a;
        });

        document.body.appendChild(button);
        document.body.appendChild(panel);

        function setOpen(open) {
            panel.hidden = !open;
            button.setAttribute("aria-expanded", String(open));
        }

        /* "current" is the last heading above the reading line, not the first one on
           screen: that is the section whose text the reader is actually inside. */
        function markCurrent() {
            var current = headings[0];
            for (var i = 0; i < headings.length; i++) {
                if (headings[i].getBoundingClientRect().top < 120) {
                    current = headings[i];
                }
            }
            links.forEach(function (a) {
                a.classList.toggle("current", a.getAttribute("href") === "#" + current.parentElement.id);
            });
        }

        /* On a pointer device the pointer arrives before the click, so a click that
           follows a hover-open must not read as "close what I just asked for". */
        var openedByHover = false;
        button.addEventListener("click", function () {
            if (panel.hidden) {
                setOpen(true);
                markCurrent();
            } else if (openedByHover) {
                openedByHover = false;
            } else {
                setOpen(false);
            }
        });

        /* Where a real pointer exists, hovering is the natural ask — open on enter, close
           a beat after the pointer has left both the pill and the panel, so the diagonal
           move between them survives. Touch keeps tap-to-toggle; click and Escape work
           everywhere, so keyboards lose nothing. */
        if (window.matchMedia("(hover: hover) and (pointer: fine)").matches) {
            var closeTimer = null;
            var hoverOpen = function () {
                clearTimeout(closeTimer);
                if (panel.hidden) {
                    openedByHover = true;
                    setOpen(true);
                    markCurrent();
                }
            };
            var hoverClose = function () {
                clearTimeout(closeTimer);
                closeTimer = setTimeout(function () {
                    setOpen(false);
                }, 200);
            };
            [button, panel].forEach(function (el) {
                el.addEventListener("mouseenter", hoverOpen);
                el.addEventListener("mouseleave", hoverClose);
            });
        }
        panel.addEventListener("click", function (event) {
            var entry = event.target.closest("a");
            if (!entry) {
                return;
            }
            setOpen(false);
            var target = document.querySelector(entry.getAttribute("href"));
            if (target) {
                jumpTo(target);
            }
        });
        document.addEventListener("keydown", function (event) {
            if (event.key === "Escape" && !panel.hidden) {
                setOpen(false);
                button.focus();
            }
        });
        document.addEventListener("click", function (event) {
            if (!panel.hidden && !panel.contains(event.target) && !button.contains(event.target)) {
                setOpen(false);
            }
        });

        var pending = false;
        document.addEventListener("scroll", function () {
            if (panel.hidden || pending) {
                return;
            }
            pending = true;
            requestAnimationFrame(function () {
                pending = false;
                markCurrent();
            });
        }, { passive: true });
    });

    /* content-visibility renders sections lazily, at estimated sizes — so any hash
       navigation lands on an estimate and chases a target that moves as sections render.
       The cure: force everything to render for one frame, jump on real geometry, then
       hand laziness back — contain-intrinsic-size's `auto` keyword records each
       section's true size once rendered, so positions stay put afterwards. This serves
       the page TOC, arriving on a shared #link, and hash changes alike. */
    function jumpTo(target) {
        document.documentElement.classList.add("serena-toc-jumping");
        requestAnimationFrame(function () {
            target.scrollIntoView({ behavior: "instant", block: "start" });
            requestAnimationFrame(function () {
                target.scrollIntoView({ behavior: "instant", block: "start" });
                document.documentElement.classList.remove("serena-toc-jumping");
            });
        });
    }

    function jumpToLocationHash() {
        if (!location.hash) {
            return;
        }
        var target;
        try {
            target = document.querySelector(location.hash);
        } catch (error) {
            return;
        }
        if (target) {
            jumpTo(target);
        }
    }

    document.addEventListener("DOMContentLoaded", jumpToLocationHash);
    window.addEventListener("hashchange", jumpToLocationHash);
})();
