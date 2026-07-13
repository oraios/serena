import QtQuick 2.15

Rectangle {
    id: root
    width: 200
    height: root.width
    color: "green"

    Text {
        id: label
        text: root.width + "x" + root.height
        anchors.centerIn: parent
    }
}
