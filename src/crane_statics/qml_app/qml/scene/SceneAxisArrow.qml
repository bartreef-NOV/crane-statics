import QtQuick
import QtQuick.Shapes

Item {
    id: root

    required property var axis
    readonly property real dx: axis.end_x - axis.start_x
    readonly property real dy: axis.end_y - axis.start_y
    readonly property real length: Math.hypot(dx, dy)

    x: axis.start_x
    y: axis.start_y - 5
    width: length + 4
    height: 10
    rotation: Math.atan2(dy, dx) * 180 / Math.PI
    transformOrigin: Item.Left

    Shape {
        anchors.fill: parent
        preferredRendererType: Shape.CurveRenderer

        ShapePath {
            strokeColor: root.axis.color
            strokeWidth: 2
            startX: 0
            startY: 5
            PathLine { x: Math.max(0, root.length - 10); y: 5 }
        }

        ShapePath {
            fillColor: root.axis.color
            strokeColor: root.axis.color
            startX: root.length
            startY: 5
            PathLine { x: Math.max(0, root.length - 10); y: 1 }
            PathLine { x: Math.max(0, root.length - 10); y: 9 }
            PathLine { x: root.length; y: 5 }
        }
    }

    Text {
        x: root.length + 4
        y: -5
        rotation: -root.rotation
        transformOrigin: Item.TopLeft
        text: root.axis.label
        color: root.axis.color
        font.pixelSize: 12
    }
}