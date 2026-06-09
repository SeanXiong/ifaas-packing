APP_QSS = """
* {
    font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
    font-size: 13px;
    outline: 0;
}

QMainWindow, QWidget {
    background: #f6f8fb;
    color: #0f172a;
}

QMainWindow {
    border: none;
}

QWidget#qt_scrollarea_viewport {
    background: transparent;
}

QFrame#Panel {
    background: #ffffff;
    border: 1px solid #dbe4ef;
    border-radius: 14px;
}

QSplitter {
    background: #eef3f8;
}

QSplitter::handle {
    background: #eef3f8;
}

QSplitter::handle:horizontal {
    width: 12px;
}

QSplitter::handle:hover {
    background: #dbeafe;
}

QLabel#Title {
    color: #0f172a;
    font-size: 17px;
    font-weight: 700;
    background: transparent;
}

QLabel#Subtle {
    color: #64748b;
    background: transparent;
}

QLabel {
    background: transparent;
}

QLineEdit, QComboBox {
    min-height: 36px;
    padding: 0 12px;
    border: 1px solid #cbd5e1;
    border-radius: 9px;
    background: #ffffff;
    color: #0f172a;
    selection-background-color: #2563eb;
    selection-color: #ffffff;
}

QLineEdit:focus, QComboBox:focus {
    border: 1px solid #2563eb;
    background: #ffffff;
}

QLineEdit:hover, QComboBox:hover {
    border: 1px solid #93c5fd;
    background: #fbfdff;
}

QLineEdit:disabled, QComboBox:disabled {
    color: #94a3b8;
    background: #f1f5f9;
    border-color: #e2e8f0;
}

QComboBox::drop-down {
    width: 34px;
    border: none;
    border-left: 1px solid #e2e8f0;
    border-top-right-radius: 9px;
    border-bottom-right-radius: 9px;
    background: #f8fafc;
}

QComboBox::down-arrow {
    image: none;
    width: 0;
    height: 0;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid #64748b;
    margin-right: 12px;
}

QComboBox QAbstractItemView {
    color: #0f172a;
    background: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 9px;
    padding: 6px;
    selection-background-color: #dbeafe;
    selection-color: #1d4ed8;
}

QTabWidget::pane {
    border: none;
    background: transparent;
}

QTabBar::tab {
    min-height: 30px;
    color: #64748b;
    padding: 7px 14px;
    margin-right: 6px;
    border: 1px solid transparent;
    border-radius: 9px;
    background: transparent;
}

QTabBar::tab:hover {
    color: #1d4ed8;
    background: #eff6ff;
    border-color: #dbeafe;
}

QTabBar::tab:selected {
    color: #1d4ed8;
    background: #dbeafe;
    border-color: #bfdbfe;
    font-weight: 700;
}

QListWidget {
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    background: #f8fafc;
    padding: 6px;
    outline: none;
}

QListWidget::item {
    min-height: 42px;
    border-radius: 10px;
    margin: 3px 0;
    padding: 4px;
    background: transparent;
    color: #0f172a;
}

QListWidget::item:hover {
    background: #eff6ff;
    color: #1e3a8a;
}

QListWidget::item:selected {
    background: #dbeafe;
    color: #1d4ed8;
    border: 1px solid #bfdbfe;
}

QListWidget::item:selected:hover {
    background: #bfdbfe;
}

QPushButton {
    min-height: 36px;
    padding: 0 15px;
    border: 1px solid #cbd5e1;
    border-radius: 9px;
    background: #ffffff;
    color: #0f172a;
    font-weight: 600;
}

QPushButton:hover {
    background: #eff6ff;
    border-color: #93c5fd;
    color: #1d4ed8;
}

QPushButton:pressed {
    background: #dbeafe;
    border-color: #60a5fa;
}

QPushButton:disabled {
    color: #94a3b8;
    background: #f1f5f9;
    border-color: #e2e8f0;
}

QPushButton#PrimaryButton {
    min-height: 44px;
    background: #2563eb;
    color: #ffffff;
    border: 1px solid #2563eb;
    border-radius: 11px;
    font-size: 15px;
    font-weight: 700;
}

QPushButton#PrimaryButton:hover {
    background: #1d4ed8;
    border-color: #1d4ed8;
    color: #ffffff;
}

QPushButton#PrimaryButton:pressed {
    background: #1e40af;
    border-color: #1e40af;
}

QPushButton#StarButton {
    min-width: 30px;
    max-width: 30px;
    min-height: 30px;
    padding: 0;
    border: none;
    background: transparent;
    color: #f59e0b;
    font-size: 18px;
    font-weight: 700;
}

QPushButton#StarButton:hover {
    background: #fef3c7;
    border: none;
    color: #d97706;
}

QPushButton#StarButton:pressed {
    background: #fde68a;
}

QProgressBar {
    min-height: 8px;
    max-height: 8px;
    border: none;
    border-radius: 4px;
    background: #e2e8f0;
}

QProgressBar::chunk {
    border-radius: 4px;
    background: #2563eb;
}

QCheckBox, QRadioButton {
    spacing: 8px;
    color: #334155;
    background: transparent;
}

QCheckBox::indicator, QRadioButton::indicator {
    width: 17px;
    height: 17px;
    border: 1px solid #cbd5e1;
    background: #ffffff;
}

QCheckBox::indicator {
    border-radius: 5px;
}

QRadioButton::indicator {
    border-radius: 9px;
}

QCheckBox::indicator:hover, QRadioButton::indicator:hover {
    border-color: #60a5fa;
    background: #eff6ff;
}

QCheckBox::indicator:checked {
    background: #2563eb;
    border-color: #2563eb;
}

QRadioButton::indicator:checked {
    background: #2563eb;
    border: 5px solid #dbeafe;
}

QScrollArea {
    background: transparent;
    border: none;
}

QScrollArea > QWidget > QWidget {
    background: transparent;
}

QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 2px;
}

QScrollBar::handle:vertical {
    min-height: 38px;
    background: #cbd5e1;
    border-radius: 5px;
}

QScrollBar::handle:vertical:hover {
    background: #94a3b8;
}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {
    height: 0;
    background: transparent;
}

QScrollBar:horizontal {
    background: transparent;
    height: 10px;
    margin: 2px;
}

QScrollBar::handle:horizontal {
    min-width: 38px;
    background: #cbd5e1;
    border-radius: 5px;
}

QScrollBar::handle:horizontal:hover {
    background: #94a3b8;
}

QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal,
QScrollBar::sub-page:horizontal {
    width: 0;
    background: transparent;
}

QStatusBar {
    background: #ffffff;
    color: #475569;
    border-top: 1px solid #e2e8f0;
}

QDialog {
    background: #f6f8fb;
}

QMessageBox {
    background: #ffffff;
}

QDialogButtonBox QPushButton {
    min-width: 84px;
}
"""
