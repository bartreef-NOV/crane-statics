import QtQuick
import QtQuick.Controls.Fusion
import QtQuick.Shapes
import ".."
import "../../design" as Design

Item {
    id: root

    property var frame: sceneVm.sceneFrame
    property color backgroundColor: Design.DesignTokens.colors.surface
    readonly property var fitRect: frame && frame.fitRect
        ? frame.fitRect : { "x": 0, "y": 0, "width": 1, "height": 1 }
    readonly property real sceneScale: Math.min(
        width / Math.max(1, fitRect.width),
        height / Math.max(1, fitRect.height)
    )
    readonly property real effectiveScale: sceneScale * zoom
    readonly property var waterline: frame && frame.waterline ? frame.waterline : null
    readonly property var status: frame && frame.status ? frame.status : null
    readonly property string mslLabelText: waterline && waterline.scene_y !== undefined && waterline.z_msl !== undefined
        ? `MSL  z = ${waterline.z_msl.toFixed(1)} m` : ""
    readonly property int mslLabelY: waterline && waterline.scene_y !== undefined
        ? Math.round(mapSceneY(waterline.scene_y)) : 0
    readonly property color mslLabelColor: Design.DesignTokens.colors.info

    Component.onDestruction: {
    }

    property real zoom: 1
    property real panX: 0
    property real panY: 0
    property real dragOriginX: 0
    property real dragOriginY: 0
    property string activeDragKind: ""
    property string hoverDragKind: ""

    function mapSceneX(value) {
        return sceneLayer.x + value * effectiveScale
    }

    function mapSceneY(value) {
        return sceneLayer.y + value * effectiveScale
    }

    function baseSceneX(scale) {
        return (width - fitRect.width * scale) / 2 - fitRect.x * scale
    }

    function baseSceneY(scale) {
        return (height - fitRect.height * scale) / 2 - fitRect.y * scale
    }

    function fitView() {
        zoom = 1
        panX = 0
        panY = 0
    }

    function fitAll() {
        fitView()
    }

    function zoomAt(itemX, itemY, factor) {
        const point = scenePointAt(itemX, itemY)
        const newZoom = Math.max(0.1, Math.min(20, zoom * factor))
        if (newZoom === zoom)
            return
        const newScale = sceneScale * newZoom
        panX = itemX - point.x * newScale - baseSceneX(newScale)
        panY = itemY - point.y * newScale - baseSceneY(newScale)
        zoom = newZoom
    }

    function nodeOverlapsCg(node) {
        const markers = frame && frame.markers ? frame.markers : []
        for (let index = 0; index < markers.length; ++index) {
            const marker = markers[index]
            if (Math.hypot(node.scene_x - marker.scene_x, node.scene_y - marker.scene_y)
                    <= marker.radius + 4)
                return true
        }
        return false
    }

    function scenePointAt(itemX, itemY) {
        return {
            "x": (itemX - sceneLayer.x) / effectiveScale,
            "y": (itemY - sceneLayer.y) / effectiveScale
        }
    }

    function dragTargetAt(itemX, itemY) {
        const point = scenePointAt(itemX, itemY)
        return sceneVm.sceneDragTargetAt(point.x, point.y)
    }

    function distanceToSegment(point, startX, startY, endX, endY) {
        const dx = endX - startX
        const dy = endY - startY
        const lengthSquared = dx * dx + dy * dy
        const ratio = lengthSquared === 0 ? 0 : Math.max(0, Math.min(1,
            ((point.x - startX) * dx + (point.y - startY) * dy) / lengthSquared))
        return Math.hypot(point.x - (startX + ratio * dx), point.y - (startY + ratio * dy))
    }

    function distanceToArc(point, moment) {
        const distance = Math.hypot(point.x - moment.origin_x, point.y - moment.origin_y)
        return Math.abs(distance - moment.radius)
    }

    function tooltipAt(itemX, itemY) {
        const point = scenePointAt(itemX, itemY)
        const groups = [
            [frame && frame.nodes ? frame.nodes : [], 5],
            [frame && frame.markers ? frame.markers : [], -1],
            [frame && frame.ropeSegments ? frame.ropeSegments : [], 0],
            [frame && frame.structuralSegments ? frame.structuralSegments : [], 0],
            [frame && frame.forceArrows ? frame.forceArrows : [], 5]
        ]
        for (let groupIndex = 0; groupIndex < groups.length; ++groupIndex) {
            const items = groups[groupIndex][0]
            for (let index = items.length - 1; index >= 0; --index) {
                const item = items[index]
                if (item.radius !== undefined
                        && Math.hypot(point.x - item.scene_x, point.y - item.scene_y) <= item.radius)
                    return item.tooltip || ""
                if (item.scene_x !== undefined
                        && Math.hypot(point.x - item.scene_x, point.y - item.scene_y) <= groups[groupIndex][1])
                    return item.tooltip || ""
                if (item.start_x !== undefined
                        && distanceToSegment(point, item.start_x, item.start_y, item.end_x, item.end_y)
                            <= Math.max(4, (item.width || groups[groupIndex][1]) / 2 + 2))
                    return item.tooltip || ""
                if (item.origin_x !== undefined
                        && distanceToSegment(point, item.origin_x, item.origin_y, item.tip_x, item.tip_y)
                            <= groups[groupIndex][1])
                    return item.tooltip || ""
            }
        }
        const moments = frame && frame.moments ? frame.moments : []
        for (let index = moments.length - 1; index >= 0; --index) {
            const moment = moments[index]
            if (distanceToArc(point, moment) <= 4
                    || Math.hypot(point.x - moment.arrow_tip_x, point.y - moment.arrow_tip_y) <= 8)
                return moment.tooltip || ""
        }
        const axes = frame && frame.boomAxes ? frame.boomAxes : []
        for (let index = axes.length - 1; index >= 0; --index) {
            const axis = axes[index]
            if (distanceToSegment(point, axis.start_x, axis.start_y, axis.end_x, axis.end_y) <= 5)
                return qsTr("Drag to set boom angle")
        }
        const guides = frame && frame.guides ? frame.guides : []
        for (let index = guides.length - 1; index >= 0; --index) {
            const guide = guides[index]
            if (guide.kind === "outreach" && Math.abs(point.x - guide.scene_x) <= 5)
                return guide.label
            if (guide.kind === "hook_height" && Math.abs(point.y - guide.scene_y) <= 5)
                return guide.label
        }
        const labels = frame && frame.labels ? frame.labels : []
        for (let index = labels.length - 1; index >= 0; --index) {
            const label = labels[index]
            if (Math.hypot(point.x - label.scene_x, point.y - label.scene_y) <= 12)
                return label.text
        }
        return ""
    }

    clip: true
    activeFocusOnTab: true
    Accessible.name: qsTr("Qt Quick crane scene canvas")

    Label {
        anchors.centerIn: parent
        visible: root.status !== null
        text: root.status ? root.status.text : ""
        color: root.status ? root.status.color : "transparent"
    }

    Rectangle {
        visible: root.waterline !== null
        x: 0
        y: root.waterline ? root.mapSceneY(root.waterline.scene_y) : 0
        width: root.width
        height: Math.max(0, root.height - y)
        color: Design.DesignTokens.colorWithAlpha(Design.DesignTokens.colors.info, 0.19)
        antialiasing: true
        z: -2
    }

    Rectangle {
        visible: root.waterline !== null
        x: 0
        y: root.waterline ? root.mapSceneY(root.waterline.scene_y) : 0
        width: root.width
        height: 2
        color: Design.DesignTokens.colors.info
        antialiasing: true
        z: -1
    }

    Item {
        id: sceneLayer
        x: root.baseSceneX(root.effectiveScale) + root.panX
        y: root.baseSceneY(root.effectiveScale) + root.panY
        scale: root.effectiveScale
        transformOrigin: Item.TopLeft

        Repeater {
            model: root.frame ? root.frame.structuralSegments : []

            delegate: Rectangle {
                required property var modelData
                readonly property real dx: modelData.end_x - modelData.start_x
                readonly property real dy: modelData.end_y - modelData.start_y
                x: modelData.start_x
                y: modelData.start_y - height / 2
                width: Math.hypot(dx, dy)
                height: modelData.width
                color: modelData.color
                antialiasing: true
                rotation: Math.atan2(dy, dx) * 180 / Math.PI
                transformOrigin: Item.Left
            }
        }

        Repeater {
            model: root.frame ? root.frame.ropeSegments : []

            delegate: Rectangle {
                required property var modelData
                readonly property real dx: modelData.end_x - modelData.start_x
                readonly property real dy: modelData.end_y - modelData.start_y
                x: modelData.start_x
                y: modelData.start_y - height / 2
                width: Math.hypot(dx, dy)
                height: modelData.width
                color: modelData.color
                antialiasing: true
                rotation: Math.atan2(dy, dx) * 180 / Math.PI
                transformOrigin: Item.Left
            }
        }

        Repeater {
            model: root.frame ? root.frame.markers : []

            delegate: SceneCgMarker {
                required property var modelData
                marker: modelData
            }
        }

        Repeater {
            model: root.frame ? root.frame.nodes : []

            delegate: SceneNodeMarker {
                required property var modelData
                visible: !root.nodeOverlapsCg(modelData)
                node: modelData
            }
        }

        Repeater {
            model: root.frame ? root.frame.forceArrows : []

            delegate: SceneForceArrow {
                required property var modelData
                arrow: modelData
            }
        }

        Repeater {
            model: root.frame ? root.frame.moments : []

            delegate: SceneMomentGlyph {
                required property var modelData
                moment: modelData
            }
        }

        Repeater {
            model: root.frame ? root.frame.boomAxes : []

            delegate: SceneAxisArrow {
                required property var modelData
                axis: modelData
            }
        }
    }

    Repeater {
        model: root.frame ? root.frame.guides : []

        delegate: Item {
            required property var modelData
            readonly property bool isOutreach: modelData.kind === "outreach"
            readonly property real anchorX: root.mapSceneX(modelData.scene_x)
            readonly property real anchorY: root.mapSceneY(modelData.scene_y)

            Shape {
                id: outreachGuideLine
                visible: parent.isOutreach
                x: parent.anchorX - 0.5
                y: parent.anchorY
                width: 2
                height: Math.max(0, guideLabel.y - y)
                antialiasing: true

                ShapePath {
                    strokeColor: Design.DesignTokens.colors.textSecondary
                    strokeWidth: 1
                    strokeStyle: ShapePath.DashLine
                    dashPattern: [4, 3]
                    startX: 0.5
                    startY: 0
                    PathLine { x: 0.5; y: outreachGuideLine.height }
                }
            }

            Shape {
                id: hookHeightGuideLine
                visible: !parent.isOutreach
                x: parent.anchorX
                y: parent.anchorY - 0.5
                width: Math.max(0, guideLabel.x - x)
                height: 2
                antialiasing: true

                ShapePath {
                    strokeColor: Design.DesignTokens.colors.textSecondary
                    strokeWidth: 1
                    strokeStyle: ShapePath.DashLine
                    dashPattern: [4, 3]
                    startX: 0
                    startY: 0.5
                    PathLine { x: hookHeightGuideLine.width; y: 0.5 }
                }
            }

            Rectangle {
                id: guideLabel
                readonly property real paddingX: 5
                readonly property real paddingY: 2
                readonly property real rightMargin: 8
                readonly property real bottomMargin: 6
                x: parent.isOutreach
                    ? Math.max(0, Math.min(root.width - width, parent.anchorX - width / 2))
                    : root.width - width - rightMargin
                y: parent.isOutreach
                    ? root.height - height - bottomMargin
                    : Math.max(0, Math.min(root.height - height, parent.anchorY - height / 2))
                width: guideText.implicitWidth + paddingX * 2
                height: guideText.implicitHeight + paddingY * 2
                radius: 4
                color: Design.DesignTokens.colors.surfaceAlt
                border.color: Design.DesignTokens.colors.border
                border.width: 1
                antialiasing: true

                Text {
                    id: guideText
                    anchors.centerIn: parent
                    text: parent.parent.modelData.label
                    color: Design.DesignTokens.colors.textPrimary
                    font.bold: true
                    font.pixelSize: 12
                }
            }
        }
    }

    Repeater {
        model: root.frame ? root.frame.labels : []

        delegate: Text {
            required property var modelData
            x: root.mapSceneX(modelData.scene_x)
            y: root.mapSceneY(modelData.scene_y)
            text: modelData.text
            color: modelData.color
            font.pixelSize: 12
        }
    }

    Label {
        x: 8
        y: root.waterline ? root.mapSceneY(root.waterline.scene_y) - height - 2 : 0
        text: root.waterline ? root.waterline.label : ""
        visible: text.length > 0
        color: Design.DesignTokens.colors.info
        padding: 2
    }

    HoverHandler {
        cursorShape: root.hoverDragKind === "outreach" ? Qt.SizeHorCursor
            : root.hoverDragKind === "tackle_length" ? Qt.SizeVerCursor
            : root.hoverDragKind === "boom_angle" ? Qt.OpenHandCursor
            : Qt.ArrowCursor
        onPointChanged: {
            root.hoverDragKind = root.dragTargetAt(point.position.x, point.position.y)
            const tip = root.tooltipAt(point.position.x, point.position.y)
            if (tip !== quickTooltip.text) {
                quickTooltip.text = tip
                quickTooltip.visible = tip.length > 0
            }
            quickTooltip.x = Math.max(
                8,
                Math.min(root.width - quickTooltip.width - 8, point.position.x + 16)
            )
            quickTooltip.y = Math.max(
                8,
                Math.min(root.height - quickTooltip.height - 8, point.position.y + 16)
            )
        }
        onHoveredChanged: if (!hovered) {
            root.hoverDragKind = ""
            quickTooltip.visible = false
        }
    }

    ToolTip {
        id: quickTooltip
        visible: false
        delay: 300
    }

    WheelHandler {
        acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
        onWheel: event => {
            const factor = event.angleDelta.y > 0 ? 1.12 : 1 / 1.12
            root.zoomAt(event.x, event.y, factor)
        }
    }

    DragHandler {
        target: null
        acceptedButtons: Qt.MiddleButton
        onActiveChanged: if (active) {
            root.dragOriginX = root.panX
            root.dragOriginY = root.panY
        }
        onTranslationChanged: {
            root.panX = root.dragOriginX + translation.x
            root.panY = root.dragOriginY + translation.y
        }
    }

    DragHandler {
        id: geometryDrag
        target: null
        acceptedButtons: Qt.LeftButton
        grabPermissions: PointerHandler.CanTakeOverFromAnything
            | PointerHandler.ApprovesTakeOverByAnything
        onActiveChanged: {
            if (active) {
                const point = root.scenePointAt(centroid.pressPosition.x, centroid.pressPosition.y)
                root.activeDragKind = root.dragTargetAt(centroid.pressPosition.x, centroid.pressPosition.y)
                if (root.activeDragKind.length > 0)
                    sceneVm.sceneDragStart(root.activeDragKind, point.x, point.y)
            } else if (root.activeDragKind.length > 0) {
                sceneVm.sceneDragEnd()
                root.activeDragKind = ""
            }
        }
        onTranslationChanged: {
            if (root.activeDragKind.length > 0) {
                const point = root.scenePointAt(centroid.position.x, centroid.position.y)
                sceneVm.sceneDragUpdate(
                    point.x,
                    point.y,
                    (centroid.modifiers & Qt.AltModifier) !== 0
                )
            }
        }
    }

    TapHandler {
        acceptedButtons: Qt.LeftButton
        onDoubleTapped: root.fitView()
    }

    TapHandler {
        acceptedButtons: Qt.RightButton
        onTapped: eventPoint => quickSceneMenu.popup(
            quickSceneMenu.parent.mapFromItem(root, eventPoint.position)
        )
    }

    Menu {
        id: quickSceneMenu

        Menu {
            title: qsTr("Overlays")

            Repeater {
                model: [
                    { key: "show_hook_forces", label: qsTr("Hook Force") },
                    { key: "show_gravity_forces", label: qsTr("Gravity Forces") },
                    { key: "show_wind_forces", label: qsTr("Wind Forces") },
                    { key: "show_inertia_forces", label: qsTr("Inertia Forces") },
                    { key: "show_reaction_forces", label: qsTr("Reactions") },
                    { key: "show_labels", label: qsTr("Labels") }
                ]

                MenuItem {
                    required property var modelData
                    text: modelData.label
                    checkable: true
                    checked: sceneVm.displayOptions[modelData.key] === true
                    onTriggered: sceneVm.setDisplayOption(modelData.key, checked)
                }
            }
        }

        Menu {
            title: qsTr("Force Scale")

            Repeater {
                model: [
                    { key: "hybrid", label: qsTr("Hybrid") },
                    { key: "physical", label: qsTr("Physical") },
                    { key: "fixed", label: qsTr("Fixed") }
                ]

                MenuItem {
                    required property var modelData
                    text: modelData.label
                    checkable: true
                    checked: sceneVm.displayOptions.force_scale_mode === modelData.key
                    onTriggered: sceneVm.setDisplayOption("force_scale_mode", modelData.key)
                }
            }
        }

        Menu {
            title: qsTr("Freebody diagrams")

            Repeater {
                model: [
                    { key: "platform", label: qsTr("Platform") },
                    { key: "boom", label: qsTr("Boom") },
                    { key: "front_leg", label: qsTr("Front Leg") },
                    { key: "rear_leg", label: qsTr("Rear Leg") }
                ]

                MenuItem {
                    required property var modelData
                    text: modelData.label
                    checkable: true
                    checked: sceneVm.displayOptions.selected_freebody === modelData.key
                    onTriggered: sceneVm.toggleFreebody(modelData.key)
                }
            }
        }

        MenuSeparator {}

        MenuItem {
            text: qsTr("Equilibrium Check")
            onTriggered: sceneVm.requestEquilibriumCheck()
        }

        MenuItem {
            text: qsTr("Load Summary")
            onTriggered: sceneVm.requestLoadSummary()
        }

        MenuItem {
            text: qsTr("Fit View")
            onTriggered: root.fitView()
        }
    }

    ReportDialog {
        id: quickReportDialog
        model: sceneVm.reportModel
    }

    LoadOverviewDialog {
        id: quickOverviewDialog
    }

    Connections {
        target: sceneVm

        function onReportReady(title, verdict) {
            quickReportDialog.title = verdict.length > 0 ? title + " — " + verdict : title
            quickReportDialog.open()
        }

        function onLoadOverviewReady(overview) {
            quickOverviewDialog.showOverview(overview)
        }
    }

    Keys.onPressed: event => {
        if (event.key === Qt.Key_R) {
            root.fitView()
            event.accepted = true
        } else if (event.key === Qt.Key_Left || event.key === Qt.Key_Down) {
            sceneVm.nudgeOutreach(event.modifiers & Qt.ShiftModifier ? -0.2 : -1.0)
            event.accepted = true
        } else if (event.key === Qt.Key_Right || event.key === Qt.Key_Up) {
            sceneVm.nudgeOutreach(event.modifiers & Qt.ShiftModifier ? 0.2 : 1.0)
            event.accepted = true
        }
    }
}