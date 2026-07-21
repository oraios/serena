import QtQuick 2.15

Rectangle {
    id: customRect
    width: 200
    height: 100
    color: "lightblue"

    Text {
        id: label
        text: "Hello QML"
        anchors.centerIn: parent
    }
}
