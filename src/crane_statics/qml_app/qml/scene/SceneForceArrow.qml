import QtQuick
import QtQuick.Shapes

Item {
    id: root

    required property var arrow
    readonly property real dx: arrow.tip_x - arrow.origin_x
    readonly property real dy: arrow.tip_y - arrow.origin_y
    readonly property real length: Math.hypot(dx, dy)

    x: arrow.origin_x
    y: arrow.origin_y - 5
    width: length
    height: 10
    antialiasing: true
    rotation: Math.atan2(dy, dx) * 180 / Math.PI
    transformOrigin: Item.Left

    Shape {
        anchors.fill: parent
        preferredRendererType: Shape.CurveRenderer

        ShapePath {
            strokeColor: root.arrow.color
            strokeWidth: 2
            strokeStyle: root.arrow.dashed ? ShapePath.DashLine : ShapePath.SolidLine
            startX: 0
            startY: 5
            PathLine { x: Math.max(0, root.length - 10); y: 5 }
        }

        ShapePath {
            fillColor: root.arrow.color
            strokeColor: root.arrow.color
            startX: root.length
            startY: 5
            PathLine { x: Math.max(0, root.length - 10); y: 1 }
            PathLine { x: Math.max(0, root.length - 10); y: 9 }
            PathLine { x: root.length; y: 5 }
        }
    }
}