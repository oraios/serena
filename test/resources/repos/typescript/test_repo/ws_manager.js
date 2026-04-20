/**
 * Dummy WebSocket manager class for testing ambiguous regex matching.
 */
class WebSocketManager {
    constructor() {
        console.log("WebSocketManager initializing\nStatus OK");
        this.ws = null;
        this.statusElement = document.getElementById("status");
    }

    /**
     * Connects to the WebSocket server.
     */
    connectToServer() {
        if (this.ws?.readyState === WebSocket.OPEN) {
            this.updateConnectionStatus("Already connected", true);
            return;
        }

        try {
            this.ws = new WebSocket("ws://localhost:4402");
            this.updateConnectionStatus("Connecting...", false);

            this.ws.onopen = () => {
                console.log("Connected to server");
                this.updateConnectionStatus("Connected", true);
            };

            this.ws.onmessage = (event) => {
                console.log("Received message:", event.data);
                try {
                    const data = JSON.parse(event.data);
                    this.handleMessage(data);
                } catch (error) {
                    console.error("Failed to parse message:", error);
                    this.updateConnectionStatus("Parse error", false);
                }
            };

            this.ws.onclose = (event) => {
                console.log("Connection closed");
                const message = event.reason || undefined;
                this.updateConnectionStatus("Disconnected", false, message);
                this.ws = null;
            };

            this.ws.onerror = (error) => {
                console.error("WebSocket error:", error);
                this.updateConnectionStatus("Connection error", false);
            };
        } catch (error) {
            console.error("Failed to connect to server:", error);
            this.updateConnectionStatus("Connection failed", false);
        }
    }

    /**
     * Updates the connection status display.
     */
    updateConnectionStatus(status, isConnected, message) {
        if (this.statusElement) {
            const text = message ? `${status}: ${message}` : status;
            this.statusElement.textContent = text;
            this.statusElement.style.color = isConnected ? "green" : "red";
        }
    }

    /**
     * Handles incoming messages.
     */
    handleMessage(data) {
        console.log("Handling:", data);
    }
}