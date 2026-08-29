import QtQuick
import QtQuick.Shapes

Item {
    id: root

    required property var marker
    readonly property real radius: marker.radius

    x: marker.scene_x - radius
    y: marker.scene_y - radius
    width: radius * 2
    height: width
    antialiasing: true

    Shape {
        anchors.fill: parent
        preferredRendererType: Shape.CurveRenderer

        ShapePath {
            fillColor: "black"
            strokeColor: "transparent"
            startX: root.radius
            startY: root.radius
            PathAngleArc {
                centerX: root.radius
                centerY: root.radius
                radiusX: root.radius
                radiusY: root.radius
                startAngle: 0
                sweepAngle: 90
                moveToStart: false
            }
            PathLine { x: root.radius; y: root.radius }
        }

        ShapePath {
            fillColor: "white"
            strokeColor: "transparent"
            startX: root.radius
            startY: root.radius
            PathAngleArc {
                centerX: root.radius
                centerY: root.radius
                radiusX: root.radius
                radiusY: root.radius
                startAngle: 90
                sweepAngle: 90
                moveToStart: false
            }
            PathLine { x: root.radius; y: root.radius }
        }

        ShapePath {
            fillColor: "black"
            strokeColor: "transparent"
            startX: root.radius
            startY: root.radius
            PathAngleArc {
                centerX: root.radius
                centerY: root.radius
                radiusX: root.radius
                radiusY: root.radius
                startAngle: 180
                sweepAngle: 90
                moveToStart: false
            }
            PathLine { x: root.radius; y: root.radius }
        }

        ShapePath {
            fillColor: "white"
            strokeColor: "transparent"
            startX: root.radius
            startY: root.radius
            PathAngleArc {
                centerX: root.radius
                centerY: root.radius
                radiusX: root.radius
                radiusY: root.radius
                startAngle: 270
                sweepAngle: 90
                moveToStart: false
            }
            PathLine { x: root.radius; y: root.radius }
        }
    }

    Shape {
        anchors.fill: parent
        preferredRendererType: Shape.CurveRenderer

        ShapePath {
            fillColor: "transparent"
            strokeColor: "black"
            strokeWidth: 1.3
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
