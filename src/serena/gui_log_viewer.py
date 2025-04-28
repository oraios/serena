# mypy: ignore-errors
import logging
import queue
import sys
import threading
import time
import tkinter as tk
import traceback
from enum import Enum, auto
from pathlib import Path

log = logging.getLogger(__name__)


class LogLevel(Enum):
    DEBUG = auto()
    INFO = auto()
    WARNING = auto()
    ERROR = auto()
    DEFAULT = auto()


class GuiLogViewer:
    """
    A class that creates a Tkinter GUI for displaying log messages in a separate thread.
    The log viewer supports coloring based on log levels (DEBUG, INFO, WARNING, ERROR).
    It can also highlight tool names in boldface when they appear in log messages.
    """

    def __init__(self, title="Log Viewer", width=800, height=600):
        """
        Initialize the ThreadedLogViewer.

        Args:
            title (str): The title of the window
            width (int): Initial window width
            height (int): Initial window height

        """
        self.title = title
        self.width = width
        self.height = height
        self.message_queue = queue.Queue()
        self.running = False
        self.log_thread = None
        self.tool_names = []  # List to store tool names for highlighting

        # Define colors for different log levels
        self.log_colors = {
            LogLevel.DEBUG: "#808080",  # Gray
            LogLevel.INFO: "#000000",  # Black
            LogLevel.WARNING: "#FF8C00",  # Dark Orange
            LogLevel.ERROR: "#FF0000",  # Red
            LogLevel.DEFAULT: "#000000",  # Black
        }

    def print_status(self, s):
        print(s + "\n", file=sys.stderr)

    def start(self):
        """Start the log viewer in a separate thread."""
        if not self.running:
            self.print_status("Starting thread")
            self.log_thread = threading.Thread(target=self.run_gui)
            self.log_thread.daemon = True
            self.log_thread.start()
            return True
        return False

    def stop(self):
        """Stop the log viewer."""
        if self.running:
            # Add a sentinel value to the queue to signal the GUI to exit
            self.message_queue.put(None)
            return True
        return False

    def set_tool_names(self, tool_names):
        """
        Set or update the list of tool names to be highlighted in log messages.

        Args:
            tool_names (list): A list of tool name strings to highlight

        """
        self.tool_names = tool_names

    def add_log(self, message):
        """
        Add a log message to the viewer.

        Args:
            message (str): The log message to display

        """
        self.message_queue.put(message)

    def _determine_log_level(self, message):
        """
        Determine the log level from the message.

        Args:
            message (str): The log message

        Returns:
            LogLevel: The determined log level

        """
        message_upper = message.upper()
        if message_upper.startswith("DEBUG"):
            return LogLevel.DEBUG
        elif message_upper.startswith("INFO"):
            return LogLevel.INFO
        elif message_upper.startswith("WARNING"):
            return LogLevel.WARNING
        elif message_upper.startswith("ERROR"):
            return LogLevel.ERROR
        else:
            return LogLevel.DEFAULT

    def _process_queue(self):
        """Process messages from the queue and update the text widget."""
        try:
            while not self.message_queue.empty():
                message = self.message_queue.get_nowait()

                # Check for sentinel value to exit
                if message is None:
                    self.root.quit()
                    return

                # Check if scrollbar is at the bottom before adding new text
                # Get current scroll position
                current_position = self.text_widget.yview()
                # If near the bottom (allowing for small floating point differences)
                was_at_bottom = current_position[1] > 0.99

                log_level = self._determine_log_level(message)

                # Insert the message at the end of the text with appropriate log level tag
                self.text_widget.configure(state=tk.NORMAL)

                # Find tool names in the message and highlight them
                if self.tool_names:
                    # Capture start position (before insertion)
                    start_index = self.text_widget.index("end-1c")

                    # Insert the message
                    self.text_widget.insert(tk.END, message + "\n", log_level.name)

                    # Convert start index to line/char format
                    line, char = map(int, start_index.split("."))

                    # Search for tool names in the message string directly
                    for tool_name in self.tool_names:
                        start_offset = 0
                        while True:
                            found_at = message.find(tool_name, start_offset)
                            if found_at == -1:
                                break

                            # Calculate line/column from offset
                            offset_line = line
                            offset_char = char
                            for c in message[:found_at]:
                                if c == "\n":
                                    offset_line += 1
                                    offset_char = 0
                                else:
                                    offset_char += 1

                            # Construct index positions
                            start_pos = f"{offset_line}.{offset_char}"
                            end_pos = f"{offset_line}.{offset_char + len(tool_name)}"

                            # Add tag to highlight the tool name
                            self.text_widget.tag_add("TOOL_NAME", start_pos, end_pos)

                            start_offset = found_at + len(tool_name)

                else:
                    # No tool names to highlight, just insert the message
                    self.text_widget.insert(tk.END, message + "\n", log_level.name)

                self.text_widget.configure(state=tk.DISABLED)

                # Auto-scroll to the bottom only if it was already at the bottom
                if was_at_bottom:
                    self.text_widget.see(tk.END)

            # Schedule to check the queue again
            if self.running:
                self.root.after(100, self._process_queue)

        except Exception as e:
            print(f"Error processing message queue: {e}", file=sys.stderr)
            if self.running:
                self.root.after(100, self._process_queue)

    def run_gui(self):
        """Run the GUI"""
        self.running = True
        try:
            self.root = tk.Tk()
            self.root.title(self.title)
            self.root.geometry(f"{self.width}x{self.height}")

            # Make the window resizable
            self.root.columnconfigure(0, weight=1)
            # We now have two rows - one for logo and one for text
            self.root.rowconfigure(0, weight=0)  # Logo row
            self.root.rowconfigure(1, weight=1)  # Text content row

            # Load and display the logo image
            try:
                # construct path relative to path of this file
                image_path = Path(__file__).parent.parent.parent / "resources" / "serena-logs.png"
                self.logo_image = tk.PhotoImage(file=image_path)

                # Create a label to display the logo
                self.logo_label = tk.Label(self.root, image=self.logo_image)
                self.logo_label.grid(row=0, column=0, sticky="ew")
            except Exception as e:
                print(f"Error loading logo image: {e}", file=sys.stderr)

            # Create frame to hold text widget and scrollbars
            frame = tk.Frame(self.root)
            frame.grid(row=1, column=0, sticky="nsew")
            frame.columnconfigure(0, weight=1)
            frame.rowconfigure(0, weight=1)

            # Create horizontal scrollbar
            h_scrollbar = tk.Scrollbar(frame, orient=tk.HORIZONTAL)
            h_scrollbar.grid(row=1, column=0, sticky="ew")

            # Create vertical scrollbar
            v_scrollbar = tk.Scrollbar(frame, orient=tk.VERTICAL)
            v_scrollbar.grid(row=0, column=1, sticky="ns")

            # Create text widget with horizontal scrolling
            self.text_widget = tk.Text(
                frame, wrap=tk.NONE, width=self.width, height=self.height, xscrollcommand=h_scrollbar.set, yscrollcommand=v_scrollbar.set
            )
            self.text_widget.grid(row=0, column=0, sticky="nsew")
            self.text_widget.configure(state=tk.DISABLED)  # Make it read-only

            # Configure scrollbars
            h_scrollbar.config(command=self.text_widget.xview)
            v_scrollbar.config(command=self.text_widget.yview)

            # Configure tags for different log levels with appropriate colors
            for level, color in self.log_colors.items():
                self.text_widget.tag_configure(level.name, foreground=color)

            # Configure tag for tool names
            self.text_widget.tag_configure("TOOL_NAME", background="#ffff00")

            # Set up the queue processing
            self.root.after(100, self._process_queue)

            # Handle window close
            self.root.protocol("WM_DELETE_WINDOW", self.stop)

            # Start the Tkinter event loop
            self.root.mainloop()

        except Exception as e:
            print(f"Error in GUI thread: {e}", file=sys.stderr)
        finally:
            self.running = False


class GuiLogViewerHandler(logging.Handler):
    """
    A logging handler that sends log records to a ThreadedLogViewer instance.
    This handler can be integrated with Python's standard logging module
    to direct log entries to a GUI log viewer.
    """

    def __init__(
        self,
        log_viewer: GuiLogViewer,
        level=logging.NOTSET,
        format_string: str | None = "%(levelname)-5s %(asctime)-15s %(name)s:%(funcName)s:%(lineno)d - %(message)s",
    ):
        """
        Initialize the handler with a ThreadedLogViewer instance.

        Args:
            log_viewer: A ThreadedLogViewer instance that will display the logs
            level: The logging level (default: NOTSET which captures all logs)
            format_string: the format string

        """
        super().__init__(level)
        self.log_viewer = log_viewer
        self.formatter = logging.Formatter(format_string)

        # Start the log viewer if it's not already running
        if not self.log_viewer.running:
            self.log_viewer.start()

    @classmethod
    def is_instance_registered(cls) -> bool:
        for h in logging.Logger.root.handlers:
            if isinstance(h, cls):
                return True
        return False

    def emit(self, record):
        """
        Emit a log record to the ThreadedLogViewer.

        Args:
            record: The log record to emit

        """
        try:
            # Format the record according to the formatter
            msg = self.format(record)

            # Convert the level name to a standard format for the viewer
            level_prefix = record.levelname

            # Add the appropriate prefix if it's not already there
            if not msg.startswith(level_prefix):
                msg = f"{level_prefix}: {msg}"

            self.log_viewer.add_log(msg)

        except Exception:
            self.handleError(record)

    def close(self):
        """
        Close the handler and optionally stop the log viewer.
        """
        # We don't automatically stop the log viewer here as it might
        # be used by other handlers or directly by the application
        super().close()

    def stop_viewer(self):
        """
        Explicitly stop the associated log viewer.
        """
        if self.log_viewer.running:
            self.log_viewer.stop()


def show_fatal_exception(e: Exception, duration_secs: int = 60):
    """
    Makes sure the given exception is shown in the GUI log viewer,
    either an existing instance or a new one.

    :param e: the exception to display
    :param duration_secs: the duration for which to display the error before
        terminating the program for the case where the log viewer is already present
        in a daemon thread which will terminate when the program does
    """
    if GuiLogViewerHandler.is_instance_registered():
        # show in existing daemon thread, waiting for the given duration
        log.error(f"Fatal error: {e}", exc_info=e)
        time.sleep(duration_secs)
    else:
        # show in new window in main thread (user must close it)
        log_viewer = GuiLogViewer()
        exc_info = "".join(traceback.format_exception(type(e), e, e.__traceback__))
        log_viewer.add_log(f"ERROR Fatal exception: {e}\n{exc_info}")
        log_viewer.run_gui()
