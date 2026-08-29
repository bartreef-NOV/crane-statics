import QtQuick
import "../design" as Design

Item {
    id: root

    property var visibilityByKey: ({})
    property var legendItems: []
    property var viewRanges: ({})
    property var baseRanges: ({})
    property bool panning: false
    property point panStart
    property var panRanges: ({})
    property var hoveredPoint: null
    property var pinnedPoint: null
    property real pointerX: -1
    property real pointerY: -1
    readonly property real plotLeft: 64
    readonly property real plotTop: 42
    readonly property real plotRight: 22
    readonly property real plotBottom: 50
    readonly property real plotWidth: Math.max(1, width - plotLeft - plotRight)
    readonly property real plotHeight: Math.max(1, height - plotTop - plotBottom)
    readonly property color plotBackgroundColor: Design.DesignTokens.colors.chartPlotBackground

    function seriesKeyVisible(key) {
        return visibilityByKey[key] !== false
    }

    function setSeriesVisible(key, visible) {
        const next = Object.assign({}, visibilityByKey)
        next[key] = visible
        visibilityByKey = next
        canvas.requestPaint()
    }

    function resetView() {
        baseRanges = chartVm.axisRanges
        viewRanges = baseRanges
        legendItems = collectLegendSeries()
        canvas.requestPaint()
    }

    function rebuild() {
        resetView()
    }

    function chartSeriesColor(series) {
        if (series.id === "capacity")
            return Design.DesignTokens.colors.primary
        if (series.id === "contractual")
            return Design.DesignTokens.colors.chartContractual
        if (!series.color)
            return Design.DesignTokens.colors.chartSeriesFallback
        return Design.DesignTokens.colorScheme === "dark" ? Qt.lighter(series.color, 1.45) : series.color
    }

    function collectSeries() {
        const series = []
        const limits = chartVm.limitSeries || []
        for (let i = 0; i < limits.length; ++i) {
            if (seriesKeyVisible(limits[i].id))
                series.push(Object.assign({}, limits[i], { color: chartSeriesColor(limits[i]) }))
        }
        if (seriesKeyVisible("capacity"))
            series.push({ id: "capacity", label: qsTr("Capacity"), color: Design.DesignTokens.colors.primary, points: chartVm.curvePoints || [] })
        return series
    }

    function collectLegendSeries() {
        const series = []
        const limits = chartVm.limitSeries || []
        series.push({ id: "capacity", label: qsTr("Capacity"), color: Design.DesignTokens.colors.primary, points: chartVm.curvePoints || [] })
        series.push({ id: "contractual", label: qsTr("Contractual"), color: Design.DesignTokens.colors.chartContractual, points: chartVm.markers || [] })
        for (let i = 0; i < limits.length; ++i)
            series.push(Object.assign({}, limits[i], { color: chartSeriesColor(limits[i]) }))
        return series
    }

    function mapX(value, ranges, left, plotWidth) {
        return left + (value - ranges.xMin) / Math.max(1e-9, ranges.xMax - ranges.xMin) * plotWidth
    }

    function mapY(value, ranges, top, plotHeight) {
        return top + plotHeight - (value - ranges.yMin) / Math.max(1e-9, ranges.yMax - ranges.yMin) * plotHeight
    }

    function niceStep(span, targetCount) {
        const raw = Math.max(1e-9, span) / Math.max(1, targetCount)
        const exponent = Math.floor(Math.log(raw) / Math.LN10)
        const magnitude = Math.pow(10, exponent)
        const normalized = raw / magnitude
        const factor = normalized <= 1 ? 1 : (normalized <= 2 ? 2 : (normalized <= 5 ? 5 : 10))
        return factor * magnitude
    }

    function majorTicks(minimum, maximum, targetCount) {
        if (!Number.isFinite(minimum) || !Number.isFinite(maximum) || maximum <= minimum)
            return []
        const step = niceStep(maximum - minimum, targetCount)
        const first = Math.ceil(minimum / step - 1e-9) * step
        const ticks = []
        for (let value = first; value <= maximum + step * 1e-9; value += step)
            ticks.push(value)
        return ticks
    }

    function formatTick(value, step) {
        const precision = Math.max(0, Math.min(6, Math.ceil(-Math.log(step) / Math.LN10)))
        return Number(value).toFixed(precision).replace(/\.0+$|(?<=\.[0-9]*?)0+$/, "")
    }

    function clampRange(minimum, maximum, baseMinimum, baseMaximum) {
        const baseSpan = Math.max(1e-9, baseMaximum - baseMinimum)
        const span = Math.max(baseSpan * 0.02, Math.min(baseSpan * 20, maximum - minimum))
        let nextMinimum = (minimum + maximum) / 2 - span / 2
        let nextMaximum = nextMinimum + span
        const margin = baseSpan * 2
        if (nextMinimum < baseMinimum - margin) {
            nextMinimum = baseMinimum - margin
            nextMaximum = nextMinimum + span
        }
        if (nextMaximum > baseMaximum + margin) {
            nextMaximum = baseMaximum + margin
            nextMinimum = nextMaximum - span
        }
        return { minimum: nextMinimum, maximum: nextMaximum }
    }

    function zoomAt(x, y, factor) {
        if (!viewRanges || viewRanges.xMax === undefined)
            return
        const dataX = viewRanges.xMin + (x - plotLeft) / plotWidth * (viewRanges.xMax - viewRanges.xMin)
        const dataY = viewRanges.yMax - (y - plotTop) / plotHeight * (viewRanges.yMax - viewRanges.yMin)
        const nextX = clampRange(dataX - (dataX - viewRanges.xMin) * factor,
                                 dataX + (viewRanges.xMax - dataX) * factor,
                                 baseRanges.xMin, baseRanges.xMax)
        const nextY = clampRange(dataY - (dataY - viewRanges.yMin) * factor,
                                 dataY + (viewRanges.yMax - dataY) * factor,
                                 baseRanges.yMin, baseRanges.yMax)
        viewRanges = {
            xMin: nextX.minimum, xMax: nextX.maximum,
            yMin: nextY.minimum, yMax: nextY.maximum
        }
        canvas.requestPaint()
    }

    function panBy(dx, dy) {
        if (!panRanges || !viewRanges)
            return
        const xShift = -dx / plotWidth * (panRanges.xMax - panRanges.xMin)
        const yShift = dy / plotHeight * (panRanges.yMax - panRanges.yMin)
        const nextX = clampRange(panRanges.xMin + xShift, panRanges.xMax + xShift,
                                 baseRanges.xMin, baseRanges.xMax)
        const nextY = clampRange(panRanges.yMin + yShift, panRanges.yMax + yShift,
                                 baseRanges.yMin, baseRanges.yMax)
        viewRanges = {
            xMin: nextX.minimum, xMax: nextX.maximum,
            yMin: nextY.minimum, yMax: nextY.maximum
        }
        canvas.requestPaint()
    }

    function nearestPoint(x, y) {
        const ranges = viewRanges
        const series = collectSeries()
        const candidates = []
        for (let s = 0; s < series.length; ++s) {
            const points = series[s].points || []
            for (let i = 0; i < points.length; ++i) {
                const px = mapX(points[i][0], ranges, plotLeft, plotWidth)
                const py = mapY(points[i][1], ranges, plotTop, plotHeight)
                candidates.push({
                    x: px, y: py, outreach: points[i][0], load: points[i][1],
                    label: series[s].label, color: series[s].color || Design.DesignTokens.colors.chartSeriesFallback,
                    distance: Math.hypot(px - x, py - y)
                })
            }
        }
        if (seriesKeyVisible("contractual")) {
            const markers = chartVm.markers || []
            for (let i = 0; i < markers.length; ++i) {
                const px = mapX(markers[i].outreach, ranges, plotLeft, plotWidth)
                const py = mapY(markers[i].load, ranges, plotTop, plotHeight)
                candidates.push({
                    x: px, y: py, outreach: markers[i].outreach, load: markers[i].load,
                    label: qsTr("Contractual (%1)").arg(markers[i].status),
                    color: markers[i].status === "pass" ? Design.DesignTokens.colors.chartPass : (markers[i].status === "fail" ? Design.DesignTokens.colors.chartFail : Design.DesignTokens.colors.chartPending),
                    distance: Math.hypot(px - x, py - y)
                })
            }
        }
        if (candidates.length === 0)
            return null
        candidates.sort((a, b) => a.distance - b.distance)
        return candidates[0].distance <= 28 ? candidates[0] : null
    }

    function clearPinnedPoint() {
        pinnedPoint = null
        canvas.requestPaint()
    }

    function drawLineSeries(context, points, ranges, left, top, plotWidth, plotHeight) {
        if (!points || points.length === 0)
            return
        context.beginPath()
        context.moveTo(mapX(points[0][0], ranges, left, plotWidth), mapY(points[0][1], ranges, top, plotHeight))
        for (let i = 1; i < points.length; ++i)
            context.lineTo(mapX(points[i][0], ranges, left, plotWidth), mapY(points[i][1], ranges, top, plotHeight))
        context.stroke()
    }

    function drawMarker(context, marker, ranges, left, top, plotWidth, plotHeight) {
        const colors = {
            pass: Design.DesignTokens.colors.chartPass,
            fail: Design.DesignTokens.colors.chartFail,
            pending: Design.DesignTokens.colors.chartPending
        }
        const x = mapX(marker.outreach, ranges, left, plotWidth)
        const y = mapY(marker.load, ranges, top, plotHeight)
        context.fillStyle = colors[marker.status] || Design.DesignTokens.colors.chartSeriesFallback
        context.beginPath()
        context.arc(x, y, 5, 0, 2 * Math.PI)
        context.fill()
    }

    Canvas {
        id: canvas
        objectName: "quickChartCanvas"
        anchors.fill: parent
        antialiasing: true

        onPaint: {
            const context = getContext("2d")
            const ranges = root.viewRanges
            const left = root.plotLeft
            const top = root.plotTop
            const plotWidth = root.plotWidth
            const plotHeight = root.plotHeight

            context.reset()
            context.fillStyle = Design.DesignTokens.colors.chartCanvasBackground
            context.fillRect(0, 0, width, height)
            context.fillStyle = root.plotBackgroundColor
            context.fillRect(left, top, plotWidth, plotHeight)
            const xStep = niceStep(ranges.xMax - ranges.xMin, Math.max(4, Math.floor(plotWidth / 110)))
            const yStep = niceStep(ranges.yMax - ranges.yMin, Math.max(4, Math.floor(plotHeight / 55)))
            const xTicks = majorTicks(ranges.xMin, ranges.xMax, Math.max(4, Math.floor(plotWidth / 110)))
            const yTicks = majorTicks(ranges.yMin, ranges.yMax, Math.max(4, Math.floor(plotHeight / 55)))
            context.strokeStyle = Design.DesignTokens.colors.chartGrid
            context.fillStyle = Design.DesignTokens.colors.chartAxisText
            context.font = "11px sans-serif"
            context.textBaseline = "top"
            context.textAlign = "center"
            for (let i = 0; i < xTicks.length; ++i) {
                const x = mapX(xTicks[i], ranges, left, plotWidth)
                context.beginPath()
                context.moveTo(x, top)
                context.lineTo(x, top + plotHeight)
                context.stroke()
                context.fillText(formatTick(xTicks[i], xStep), x, top + plotHeight + 8)
            }
            context.textBaseline = "middle"
            context.textAlign = "right"
            for (let i = 0; i < yTicks.length; ++i) {
                const y = mapY(yTicks[i], ranges, top, plotHeight)
                context.beginPath()
                context.moveTo(left, y)
                context.lineTo(left + plotWidth, y)
                context.stroke()
                context.fillText(formatTick(yTicks[i], yStep), left - 8, y)
            }
            context.strokeStyle = Design.DesignTokens.colors.chartAxisBorder
            context.lineWidth = 1
            context.strokeRect(left, top, plotWidth, plotHeight)

            context.fillText(qsTr("Outreach (m)"), left + plotWidth / 2, height - 20)

            context.save()
            context.translate(14, top + plotHeight / 2)
            context.rotate(-Math.PI / 2)
            context.fillText(qsTr("Load (t)"), 0, 0)
            context.restore()

            context.save()
            context.beginPath()
            context.rect(left, top, plotWidth, plotHeight)
            context.clip()

            const series = root.collectSeries()
            for (let i = 0; i < series.length; ++i) {
                context.strokeStyle = series[i].color || Design.DesignTokens.colors.chartSeriesFallback
                context.lineWidth = series[i].id === "capacity" ? 2.5 : 1.25
                root.drawLineSeries(context, series[i].points, ranges, left, top, plotWidth, plotHeight)
            }

            if (root.seriesKeyVisible("contractual")) {
                const markers = chartVm.markers || []
                for (let i = 0; i < markers.length; ++i)
                    root.drawMarker(context, markers[i], ranges, left, top, plotWidth, plotHeight)
            }
            context.restore()

            const inspected = root.pinnedPoint || root.hoveredPoint
            if (inspected) {
                context.strokeStyle = Design.DesignTokens.colors.chartCrosshair
                context.lineWidth = 1
                context.setLineDash([4, 4])
                context.beginPath()
                context.moveTo(inspected.x, top)
                context.lineTo(inspected.x, top + plotHeight)
                context.moveTo(left, inspected.y)
                context.lineTo(left + plotWidth, inspected.y)
                context.stroke()
                context.setLineDash([])

                context.fillStyle = inspected.color
                context.beginPath()
                context.arc(inspected.x, inspected.y, root.pinnedPoint ? 6 : 5, 0, 2 * Math.PI)
                context.fill()
                context.strokeStyle = Design.DesignTokens.colors.chartPlotBackground
                context.lineWidth = 2
                context.stroke()

                const text = `${inspected.label}\nOutreach: ${Number(inspected.outreach).toFixed(2)} m\nLoad: ${Number(inspected.load).toFixed(2)} t`
                const boxWidth = 174
                const boxHeight = 58
                const boxX = inspected.x > left + plotWidth - boxWidth - 8
                    ? left + 8 : left + plotWidth - boxWidth - 8
                const boxY = inspected.y < top + boxHeight + 8
                    ? top + plotHeight - boxHeight - 8 : top + 8
                context.fillStyle = Design.DesignTokens.colors.chartTooltipBackground
                context.strokeStyle = Design.DesignTokens.colors.chartTooltipBorder
                context.lineWidth = 1
                context.fillRect(boxX, boxY, boxWidth, boxHeight)
                context.strokeRect(boxX, boxY, boxWidth, boxHeight)
                context.fillStyle = Design.DesignTokens.colors.chartTooltipText
                context.font = "11px sans-serif"
                context.textAlign = "left"
                context.textBaseline = "top"
                const lines = text.split("\n")
                for (let i = 0; i < lines.length; ++i)
                    context.fillText(lines[i], boxX + 8, boxY + 8 + i * 15, boxWidth - 16)
            }
        }
    }

    Component.onCompleted: rebuild()
    onWidthChanged: canvas.requestPaint()
    onHeightChanged: canvas.requestPaint()
    onPlotBackgroundColorChanged: canvas.requestPaint()

    Connections {
        target: chartVm
        function onChartUpdated() { root.rebuild() }
        function onResetViewRequested() { root.resetView() }
    }

    MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.LeftButton | Qt.MiddleButton
        hoverEnabled: true

        onPressed: mouse => {
                if (mouse.button === Qt.MiddleButton
                    && mouse.x >= root.plotLeft && mouse.x <= root.plotLeft + root.plotWidth
                    && mouse.y >= root.plotTop && mouse.y <= root.plotTop + root.plotHeight) {
                root.panning = true
                root.panStart = Qt.point(mouse.x, mouse.y)
                root.panRanges = root.viewRanges
                cursorShape = Qt.ClosedHandCursor
            }
        }

        onPositionChanged: mouse => {
            root.pointerX = mouse.x
            root.pointerY = mouse.y
            root.hoveredPoint = root.nearestPoint(mouse.x, mouse.y)
            if (root.panning)
                root.panBy(mouse.x - root.panStart.x, mouse.y - root.panStart.y)
            canvas.requestPaint()
        }

        onEntered: {
            root.pointerX = mouseX
            root.pointerY = mouseY
            root.hoveredPoint = root.nearestPoint(mouseX, mouseY)
            canvas.requestPaint()
        }

        onExited: {
            root.pointerX = -1
            root.pointerY = -1
            root.hoveredPoint = null
            canvas.requestPaint()
        }

        onClicked: mouse => {
            if (mouse.button === Qt.LeftButton) {
                root.pinnedPoint = root.nearestPoint(mouse.x, mouse.y)
                canvas.requestPaint()
            }
        }

        onDoubleClicked: mouse => {
            if (mouse.button === Qt.LeftButton)
                root.resetView()
        }

        onReleased: {
            root.panning = false
            cursorShape = Qt.ArrowCursor
        }

        onWheel: wheel => {
            if (wheel.angleDelta.y !== 0)
                root.zoomAt(wheel.x, wheel.y, wheel.angleDelta.y > 0 ? 0.85 : 1.18)
            wheel.accepted = true
        }
    }
}
