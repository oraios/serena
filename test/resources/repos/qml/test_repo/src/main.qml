import QtQuick 2.15
import QtQuick.Controls 2.15

ApplicationWindow {
    id: mainWindow
    title: "Test Application"
    width: 800
    height: 600

    Button {
        id: mainButton
        text: "Click Me"
        width: 100
        height: 50

        onClicked: {
            console.log("Button clicked")
        }
    }
}
