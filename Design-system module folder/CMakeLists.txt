find_package(Qt6 6.5 REQUIRED COMPONENTS Qml)

qt_add_library(bf_design_system STATIC)

set_source_files_properties(
    Theme.qml
    Metrics.qml
    PROPERTIES QT_QML_SINGLETON_TYPE TRUE
)

qt_add_qml_module(bf_design_system
    URI BF.DesignSystem
    VERSION 1.0
    QML_FILES
        Theme.qml
        Metrics.qml
        BfButton.qml
        BfTextField.qml
        BfCard.qml
        BfStatusBadge.qml
        BfPage.qml
)
