import QtQuick
import QtQuick.Shapes

Item {
    id: root

    required property var moment
    readonly property real baseDegrees: moment.start_degrees + moment.span_degrees
    readonly property real baseRadians: baseDegrees * Math.PI / 180
    readonly property real baseX: moment.radius + moment.radius * Math.cos(baseRadians)
    readonly property real baseY: moment.radius - moment.radius * Math.sin(baseRadians)
    readonly property real tipX: moment.arrow_tip_x - (moment.origin_x - moment.radius)
    readonly property real tipY: moment.arrow_tip_y - (moment.origin_y - moment.radius)

    // Arrowhead wings must sit perpendicular to the arc's tangent at the base point.
    readonly property real tanX: root.tipX - root.baseX
    readonly property real tanY: root.tipY - root.baseY
    readonly property real tanLen: Math.hypot(root.tanX, root.tanY)
    readonly property real normX: root.tanLen > 0 ? -root.tanY / root.tanLen : 0
    readonly property real normY: root.tanLen > 0 ? root.tanX / root.tanLen : 0
    readonly property real wingHalf: 3.8

    x: moment.origin_x - moment.radius
    y: moment.origin_y - moment.radius
    width: moment.radius * 2 + 18
    height: moment.radius * 2 + 18

    Shape {
        anchors.fill: parent
        preferredRendererType: Shape.CurveRenderer

        ShapePath {
            strokeColor: root.moment.color
            strokeWidth: 1.8
            fillColor: "transparent"
            startX: root.moment.radius + root.moment.radius * Math.cos(root.moment.start_degrees * Math.PI / 180)
            startY: root.moment.radius - root.moment.radius * Math.sin(root.moment.start_degrees * Math.PI / 180)
            PathArc {
                x: root.baseX
                y: root.baseY
                radiusX: root.moment.radius
                radiusY: root.moment.radius
                useLargeArc: true
                direction: root.moment.span_degrees > 0 ? PathArc.Counterclockwise : PathArc.Clockwise
            }
        }

        ShapePath {
            fillColor: root.moment.color
            strokeColor: root.moment.color
            startX: root.tipX
            startY: root.tipY
            PathLine { x: root.baseX + root.normX * root.wingHalf; y: root.baseY + root.normY * root.wingHalf }
            PathLine { x: root.baseX - root.normX * root.wingHalf; y: root.baseY - root.normY * root.wingHalf }
            PathLine { x: root.tipX; y: root.tipY }
        }
    }
}