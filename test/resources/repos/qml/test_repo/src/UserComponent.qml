import QtQuick 2.15

Item {
    width: 400
    height: 300

    CustomComponent {
        x: 50
        y: 50
    }

    Rectangle {
        y: 180
        width: 200
        height: 100
        color: "yellow"

        Text {
            text: "Another shape"
            anchors.centerIn: parent
        }
    }
}
