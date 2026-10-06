import QtQuick
import QtQuick.Controls.Fusion
import QtQuick.Shapes
import ".."
import BF.DesignSystem

Item {
    id: root

    property var frame: sceneVm.sceneFrame
    property color backgroundColor: Theme.surface
    readonly property var fitRect: frame && frame.fitRect
        ? frame.fitRect : { "x": 0, "y": 0, "width": 1, "height": 1 }
    readonly property real sceneScale: Math.min(
        width / Math.max(1, fitRect.width),
        height / Math.max(1, fitRect.height)
    )
    readonly property real effectiveScale: sceneScale * zoom
    readonly property var waterline: frame && frame.waterline ? frame.waterline : null
    readonly property var status: frame && frame.status ? frame.status : null
    // Screen y of the (possibly tilted) waterline at both canvas edges.
    readonly property real waterlineLeftY: waterlineYAt(0)
    readonly property real waterlineRightY: waterlineYAt(width)

    Component.onDestruction: {
    }

    property real zoom: 1
    property real panX: 0
    property real panY: 0
    property real dragOriginX: 0
    property real dragOriginY: 0
    property string activeDragKind: ""
    property string hoverDragKind: ""
    property bool hoverPickable: false
    //: The one open tooltip, as { key, text, x, y }, or null when none is pinned.
    property var pinnedTip: null

    // A new frame renumbers everything the pinned key refers to, and may have moved
    // or removed that element outright, so the tooltip goes with the frame it named.
    onFrameChanged: pinnedTip = null

    function mapSceneX(value) {
        return sceneLayer.x + value * effectiveScale
    }

    function mapSceneY(value) {
        return sceneLayer.y + value * effectiveScale
    }

    // The scene mapping scales uniformly, so the frame's scene slope is the screen slope.
    function waterlineYAt(screenX) {
        if (!waterline)
            return 0
        return mapSceneY(waterline.scene_y)
            + waterline.slope * (screenX - mapSceneX(waterline.pivot_x))
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

    // Which drawn element a point lands on, as { key, text }, or null for none.
    // ``key`` identifies the element within the current frame, which is what lets a
    // second click on the same element close its tooltip instead of re-pinning it.
    // Only elements that carry information are pickable: the boom axes and the drag
    // guides are gestures, not readouts, and they answer with a cursor instead.
    function pickAt(itemX, itemY) {
        const point = scenePointAt(itemX, itemY)
        const groups = [
            ["nodes", frame && frame.nodes ? frame.nodes : [], 5],
            ["markers", frame && frame.markers ? frame.markers : [], -1],
            ["ropes", frame && frame.ropeSegments ? frame.ropeSegments : [], 0],
            ["structure", frame && frame.structuralSegments ? frame.structuralSegments : [], 0],
            ["forces", frame && frame.forceArrows ? frame.forceArrows : [], 5]
        ]
        for (let groupIndex = 0; groupIndex < groups.length; ++groupIndex) {
            const name = groups[groupIndex][0]
            const items = groups[groupIndex][1]
            const slack = groups[groupIndex][2]
            for (let index = items.length - 1; index >= 0; --index) {
                const item = items[index]
                let hit = false
                if (item.radius !== undefined)
                    hit = Math.hypot(point.x - item.scene_x, point.y - item.scene_y) <= item.radius
                else if (item.scene_x !== undefined)
                    hit = Math.hypot(point.x - item.scene_x, point.y - item.scene_y) <= slack
                else if (item.start_x !== undefined)
                    hit = distanceToSegment(point, item.start_x, item.start_y, item.end_x, item.end_y)
                        <= Math.max(4, (item.width || slack) / 2 + 2)
                else if (item.origin_x !== undefined)
                    hit = distanceToSegment(point, item.origin_x, item.origin_y, item.tip_x, item.tip_y)
                        <= slack
                if (hit && item.tooltip)
                    return { "key": `${name}:${index}`, "text": item.tooltip }
            }
        }
        const moments = frame && frame.moments ? frame.moments : []
        for (let index = moments.length - 1; index >= 0; --index) {
            const moment = moments[index]
            if ((distanceToArc(point, moment) <= 4
                    || Math.hypot(point.x - moment.arrow_tip_x, point.y - moment.arrow_tip_y) <= 8)
                    && moment.tooltip)
                return { "key": `moments:${index}`, "text": moment.tooltip }
        }
        return null
    }

    // Clicking an element pins its tooltip; clicking it again, or anywhere that
    // carries nothing, closes it. Only one is ever open: it is one property.
    function toggleTipAt(itemX, itemY) {
        // A drag target owns its press, so it never opens a tooltip.
        if (dragTargetAt(itemX, itemY).length > 0)
            return
        const pick = pickAt(itemX, itemY)
        if (pick === null || (pinnedTip !== null && pinnedTip.key === pick.key)) {
            pinnedTip = null
            return
        }
        pinnedTip = { "key": pick.key, "text": pick.text, "x": itemX, "y": itemY }
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

    Shape {
        id: sea
        visible: root.waterline !== null
        anchors.fill: parent
        z: -2

        readonly property real floorY: Math.max(root.height, root.waterlineLeftY, root.waterlineRightY)

        ShapePath {
            strokeColor: "transparent"
            fillColor: Theme.colorWithAlpha(Theme.info, 0.19)
            startX: 0
            startY: root.waterlineLeftY
            PathLine { x: root.width; y: root.waterlineRightY }
            PathLine { x: root.width; y: sea.floorY }
            PathLine { x: 0; y: sea.floorY }
            PathLine { x: 0; y: root.waterlineLeftY }
        }

        ShapePath {
            strokeColor: Theme.info
            strokeWidth: 2
            fillColor: "transparent"
            startX: 0
            startY: root.waterlineLeftY
            PathLine { x: root.width; y: root.waterlineRightY }
        }
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

                ShapePath {
                    strokeColor: Theme.textMuted
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

                ShapePath {
                    strokeColor: Theme.textMuted
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
                color: Theme.surfaceSubtle
                border.color: Theme.border
                border.width: 1

                Text {
                    id: guideText
                    anchors.centerIn: parent
                    text: parent.parent.modelData.label
                    color: Theme.text
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
        y: root.waterline ? root.waterlineYAt(x) - height - 2 : 0
        text: root.waterline ? root.waterline.label : ""
        visible: text.length > 0
        color: Theme.info
        padding: 2
    }

    // How much rope sits on each winch. Screen-space, so it neither pans nor scales
    // with the scene, and it accepts no pointer events -- the canvas gestures are
    // handled by handlers on root and must keep working over the card.
    Rectangle {
        id: winchSpoolCard
        objectName: "winchSpoolCard"
        readonly property var rows: root.frame && root.frame.winchSpools
            ? root.frame.winchSpools : []
        readonly property real paddingX: 8
        readonly property real paddingY: 5

        x: 8
        y: 8
        visible: rows.length > 0
        width: winchSpoolContent.implicitWidth + paddingX * 2
        height: winchSpoolContent.implicitHeight + paddingY * 2
        radius: 4
        color: Theme.surfaceSubtle
        border.color: Theme.border
        border.width: 1

        // Widest value string, so the value column can be right-aligned without
        // binding a child's width to its parent's (which would loop).
        TextMetrics {
            id: winchSpoolValueMetrics
            font.pixelSize: 12
            text: {
                let longest = ""
                for (let i = 0; i < winchSpoolCard.rows.length; ++i) {
                    const value = String(winchSpoolCard.rows[i].value_text)
                    if (value.length > longest.length)
                        longest = value
                }
                return longest
            }
        }

        Column {
            id: winchSpoolContent
            x: winchSpoolCard.paddingX
            y: winchSpoolCard.paddingY
            spacing: 3

            Text {
                text: qsTr("Rope on winches")
                color: Theme.text
                font.bold: true
                font.pixelSize: 12
            }

            Row {
                spacing: 10

                Column {
                    Repeater {
                        model: winchSpoolCard.rows

                        delegate: Text {
                            required property var modelData
                            text: modelData.hoist_id
                            color: Theme.textMuted
                            font.pixelSize: 12
                        }
                    }
                }

                Column {
                    objectName: "winchSpoolValueColumn"

                    Repeater {
                        model: winchSpoolCard.rows

                        delegate: Text {
                            required property var modelData
                            text: modelData.value_text
                            color: Theme.text
                            font.pixelSize: 12
                            width: Math.max(winchSpoolValueMetrics.width, implicitWidth)
                            horizontalAlignment: Text.AlignRight
                        }
                    }
                }
            }
        }
    }

    HoverHandler {
        cursorShape: root.hoverDragKind === "outreach" ? Qt.SizeHorCursor
            : root.hoverDragKind === "tackle_length" ? Qt.SizeVerCursor
            : root.hoverDragKind === "boom_angle" ? Qt.OpenHandCursor
            : root.hoverPickable ? Qt.PointingHandCursor
            : Qt.ArrowCursor
        onPointChanged: {
            root.hoverDragKind = root.dragTargetAt(point.position.x, point.position.y)
            root.hoverPickable = root.hoverDragKind.length === 0
                && root.pickAt(point.position.x, point.position.y) !== null
        }
        onHoveredChanged: if (!hovered) {
            root.hoverDragKind = ""
            root.hoverPickable = false
        }
    }

    ToolTip {
        id: quickTooltip
        objectName: "quickSceneTooltip"
        // Pinned, not hovered: no delay to open and no timeout to close it.
        delay: 0
        timeout: -1
        visible: root.pinnedTip !== null
        text: root.pinnedTip ? root.pinnedTip.text : ""
        x: root.pinnedTip
            ? Math.max(8, Math.min(root.width - width - 8, root.pinnedTip.x + 16))
            : 0
        y: root.pinnedTip
            ? Math.max(8, Math.min(root.height - height - 8, root.pinnedTip.y + 16))
            : 0
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
        onSingleTapped: eventPoint => root.toggleTipAt(eventPoint.position.x, eventPoint.position.y)
        // Fit-view keeps the empty canvas to itself, so double-clicking an element
        // cannot reset the view out from under the tooltip it just opened.
        onDoubleTapped: eventPoint => {
            if (root.pickAt(eventPoint.position.x, eventPoint.position.y) === null
                    && root.dragTargetAt(eventPoint.position.x, eventPoint.position.y).length === 0)
                root.fitView()
        }
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
                    { key: "show_rope_weight_forces", label: qsTr("Rope Weight") },
                    { key: "show_wind_forces", label: qsTr("Wind Forces") },
                    { key: "show_inertia_forces", label: qsTr("Inertia Forces") },
                    { key: "show_reaction_forces", label: qsTr("Reactions") },
                    { key: "show_labels", label: qsTr("Labels") },
                    { key: "show_winch_spools", label: qsTr("Rope on Winches") }
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