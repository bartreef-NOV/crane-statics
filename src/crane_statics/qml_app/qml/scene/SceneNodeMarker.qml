import QtQuick
import QtQuick.Shapes

Item {
    id: root

    required property var node
    readonly property real radius: 4

    x: node.scene_x - radius
    y: node.scene_y - radius
    width: radius * 2
    height: width

    Shape {
        anchors.fill: parent
        preferredRendererType: Shape.CurveRenderer

        ShapePath {
            fillColor: "white"
            strokeColor: "black"
            strokeWidth: 1.6
            startX: root.radius
            startY: 0
            PathAngleArc {
                centerX: root.radius
                centerY: root.radius
                radiusX: root.radius
                radiusY: root.radius
                startAngle: -90
                sweepAngle: 360
            }
        }
    }
}