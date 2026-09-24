# BF QML Design System

A small Qt 6 QML module built from the supplied BF/NOV color palette.

## Semantic defaults

- `Theme.primary`: NOV blue
- `Theme.accent`: NOV yellow
- `Theme.success`: NOV green
- `Theme.warning`: NOV orange
- `Theme.error`: NOV red
- `Theme.info`: NOV teal

All supplied raw colors are also available from `Theme`, for example:

```qml
Rectangle {
    color: Theme.novPurple
}
```

## Add it to a Qt 6 application

From the application `CMakeLists.txt`:

```cmake
add_subdirectory(path/to/qml/BF/DesignSystem)
target_link_libraries(my_app PRIVATE bf_design_system)
```

Then import and use the controls:

```qml
import QtQuick
import QtQuick.Controls
import BF.DesignSystem

ApplicationWindow {
    visible: true
    width: 720
    height: 480

    BfPage {
        anchors.fill: parent

        Column {
            spacing: Metrics.spacing16

            BfTextField {
                placeholderText: qsTr("Instrument name")
            }

            Row {
                spacing: Metrics.spacing8

                BfButton { text: qsTr("Connect") }
                BfButton { text: qsTr("Cancel"); variant: "ghost" }
                BfStatusBadge { text: qsTr("Ready"); status: "success" }
            }
        }
    }
}
```

CMake's `qt_add_qml_module` route is preferred for Qt 6 because it generates
the module metadata needed by QML tooling and compile-time type information.
